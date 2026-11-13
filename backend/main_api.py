"""
[3] Главный API-сервис Horizon Relay (FastAPI + Uvicorn uvloop + ORJSONResponse).
Реализует:
1. Атомарный Rate-Limiter (Token Bucket на Lua в Redis) с 3 тарифными зонами.
2. Защиту от Cache Stampede через распределенный коалесцер запросов SingleFlight (SET NX PX).
3. L1 In-Memory кэш (cachetools.TTLCache) для мгновенной отдачи дашборда деканата (< 1 мс).
4. Все 8 консолидированных REST/SSE эндпоинтов:
   - [1] POST /api/v1/projects/ingest (Потоковый прием PDF + SHA-256 замок идемпотентности)
   - [2] GET  /api/v1/jobs/{job_id}/stream (Redis Streams SSE + JSON Short-Polling Fallback)
   - [3] GET  /api/v1/projects (Каталог Биржи эстафеты + детальное досье и граф поколений)
   - [4] GET  /api/v1/projects/{project_id}/synergy (Асимметричный матчинг + Corporate Bounty)
   - [5] POST /api/v1/projects/{project_id}/claim (Бронирование Take the Baton с FOR UPDATE NOWAIT)
   - [6] POST /api/v1/projects/{project_id}/package (Генератор HANDOVER.md, CITATION.cff и ТЗ слияния)
   - [7] GET  /api/v1/analytics/bottlenecks (Дашборд Деканата: Treemap, Золотой резерв, TRL 6-7, FinOps)
   - [8] POST /api/v1/analytics/export-topics (1-Click экспорт банка тем ВКР, грантов и модерация доменов)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import orjson
from cachetools import TTLCache
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, PlainTextResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from config_and_db import (
    cas_storage,
    db_session_context,
    get_db_session,
    get_redis_cache,
    get_redis_state,
    init_postgres_schema,
    init_qdrant_collections,
    publish_job_stream_event,
    settings,
)
from core.lineage_packager import (
    claim_project_baton,
    generate_handover_package,
    get_project_lineage_graph,
)
from core.ontology_and_roi import (
    execute_dean_action,
    get_dean_analytics_dashboard,
)
from core.synergy_engine import find_asymmetric_synergy
from models_and_schemas import (
    AtomicDemandItem,
    AtomicSupplyItem,
    CoreProjectSchema,
    DeanActionRequest,
    PackageGenerationRequest,
    Project,
    ProjectRevision,
    ProjectStatus,
    TakeBatonRequest,
)
from workers.celery_app import celery_app, get_ingest_queue_depth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("horizon.api")

# L1 In-Process Memory Cache для аналитики деканата (TTL = 30 секунд, ответ < 1 мс)
dean_l1_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=128, ttl=30.0)


# ==============================================================================
# 1. АТОМАРНЫЙ LUA-СКРИПТ TOKEN BUCKET ДЛЯ RATE LIMITING (3 ТАРИФНЫЕ ЗОНЫ)
# ==============================================================================
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local data = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
else
    local elapsed = math.max(0, now - last_refill)
    tokens = math.min(capacity, tokens + elapsed * refill_rate)
    last_refill = now
end

if tokens >= requested then
    tokens = tokens - requested
    redis.call("HMSET", key, "tokens", tokens, "last_refill", last_refill)
    return {1, math.floor(tokens)}
else
    local wait_sec = math.ceil((requested - tokens) / refill_rate)
    redis.call("HMSET", key, "tokens", tokens, "last_refill", last_refill)
    return {0, wait_sec}
end
"""


async def enforce_rate_limit(
    request: Request,
    zone_name: str,
    capacity: float,
    refill_per_sec: float,
) -> None:
    """
    Применяет дифференцированный Token Bucket в Redis (db=0 без TTL, чтобы не вытеснялся).
    Тарифные зоны:
    - Zone_Ingest: B=5, R=0.05/s
    - Zone_External_Match: B=20, R=0.5/s
    - Zone_Read: B=100, R=5.0/s
    """
    client_ip = request.headers.get("X-Real-IP") or (
        request.client.host if request.client else "127.0.0.1"
    )
    bucket_key = f"rl:{zone_name}:{client_ip}"
    r_state = get_redis_state()
    try:
        allowed, meta_val = await r_state.eval(
            TOKEN_BUCKET_LUA,
            1,
            bucket_key,
            capacity,
            refill_per_sec,
            time.time(),
            1,
        )
        if int(allowed) == 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Превышен лимит запросов в зоне {zone_name}. Повторите через {meta_val} сек.",
                headers={"Retry-After": str(meta_val)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Rate limit Redis check bypassed: %s", exc)


# ==============================================================================
# 2. МЕХАНИЗМ SINGLEFLIGHT (ЗАЩИТА ОТ CACHE STAMPEDE НА ГРАФЕ СИНЕРГИИ)
# ==============================================================================
async def get_synergy_with_singleflight(
    db: AsyncSession,
    project_id: uuid.UUID,
    passport: CoreProjectSchema,
    bounty_query: str | None = None,
) -> dict[str, Any]:
    """
    Коалесцер конкурентных запросов (SingleFlight):
    Если 50 человек одновременно открывают граф синергии одного проекта при холодном кэше,
    только первый запрос идет в Qdrant и HuggingFace (захватывая lock в redis-state),
    а остальные 49 ждут результат из redis-cache.
    """
    rev_num = passport.revision_number
    q_suffix = hashlib.md5((bounty_query or "").encode("utf-8")).hexdigest()[:8] if bounty_query else "base"
    cache_key = f"cache:synergy:{project_id}:{rev_num}:{q_suffix}"
    lock_key = f"lock:sf:{cache_key}"

    r_cache = get_redis_cache()
    r_state = get_redis_state()

    cached_bytes = await r_cache.get(cache_key)
    if cached_bytes:
        return orjson.loads(cached_bytes)

    acquired = await r_state.set(lock_key, b"1", nx=True, px=8000)
    if acquired:
        try:
            synergy_dto = await find_asymmetric_synergy(
                db=db,
                project_id=project_id,
                passport=passport,
                custom_bounty_query=bounty_query,
            )
            payload_dict = synergy_dto.model_dump(mode="json")
            await r_cache.setex(cache_key, 7200, orjson.dumps(payload_dict))
            return payload_dict
        finally:
            await r_state.delete(lock_key)
    else:
        for _ in range(35):
            await asyncio.sleep(0.1)
            cached_bytes = await r_cache.get(cache_key)
            if cached_bytes:
                return orjson.loads(cached_bytes)

        synergy_dto = await find_asymmetric_synergy(
            db=db,
            project_id=project_id,
            passport=passport,
            custom_bounty_query=bounty_query,
        )
        return synergy_dto.model_dump(mode="json")


# ==============================================================================
# 3. LIFESPAN ИНИЦИАЛИЗАЦИЯ СЕРВИСА И АВТО-НАПОЛНЕНИЕ ДЕМО-БАЗЫ
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Initializing Horizon Relay PostgreSQL 16 schema and Qdrant FP32 collections...")
    await init_postgres_schema()
    await init_qdrant_collections()

    # Если база пуста — автоматически наполняем демонстрационным корпусом вуза (200 проектов + эталонные PDF)
    async with db_session_context() as db:
        count_res = await db.execute(select(func.count(Project.id)))
        total_existing = int(count_res.scalar_one() or 0)
        if total_existing == 0:
            logger.info("Database is empty. Running automatic dataset seeding (200 projects + flagship PDFs)...")
            from scripts.seed_demo_data import seed_university_corpus

            await seed_university_corpus(db)
            logger.info("Dataset seeding completed successfully.")

    yield


app = FastAPI(
    title="Horizon Relay API",
    description="Zero-Trust Academic Thesis Audit & Asymmetric R&D Synergy Engine",
    version="2.0.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# ЭНДПОИНТ [1]: POST /api/v1/projects/ingest (ПОТОКОВАЯ ЗАГРУЗКА PDF + DAG)
# ==============================================================================
@app.post("/api/v1/projects/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_thesis_pdf(
    request: Request,
    file: UploadFile = File(...),
    repo_url: str | None = Form(default=None),
    title: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Потоково принимает PDF-файл чанками по 64 КБ во временный буфер SpooledTemporaryFile,
    проверяет сигнатуру %PDF-1., вычисляет SHA-256 на лету, ставит атомарный замок от двойного клика
    `SET ingest_lock:{pdf_sha256} {job_id} NX EX 180` и запускает конвейер 5 воркеров.
    """
    await enforce_rate_limit(request, "Zone_Ingest", capacity=5.0, refill_per_sec=0.05)

    sha256_hasher = hashlib.sha256()
    total_bytes = 0
    max_bytes = 25 * 1024 * 1024  # 25 МБ

    with tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode="w+b") as spooled:
        first_chunk = True
        while True:
            chunk = await file.read(65536)
            if not chunk:
                break
            if first_chunk:
                if not (chunk.startswith(b"%PDF-1.") or chunk.startswith(b"%PDF-2.")):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="INVALID_PDF_SIGNATURE: Файл должен быть валидным PDF (%PDF-1.x в первых 8 байтах).",
                    )
                first_chunk = False
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="PDF_TOO_LARGE: Размер файла превышает допустимый лимит 25 МБ.",
                )
            sha256_hasher.update(chunk)
            spooled.write(chunk)

        if total_bytes < 64:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="EMPTY_FILE: Загруженный PDF-файл пуст.",
            )

        pdf_sha256 = sha256_hasher.hexdigest()
        r_state = get_redis_state()
        lock_key = f"ingest_lock:{pdf_sha256}"

        # 1. Защита от двойного клика: если этот файл уже обрабатывается прямо сейчас, возвращаем активный job_id
        existing_lock = await r_state.get(lock_key)
        if existing_lock is not None:
            active_info = orjson.loads(existing_lock)
            return {
                "job_id": active_info["job_id"],
                "project_id": active_info["project_id"],
                "revision_id": active_info["revision_id"],
                "status": "ALREADY_PROCESSING_ATTACHED",
                "sse_url": f"/api/v1/jobs/{active_info['job_id']}/stream",
            }

        spooled.seek(0)
        pdf_bytes = spooled.read()

    _, saved_pdf_path = cas_storage.save_pdf_bytes(pdf_bytes, sha256_hex=pdf_sha256)

    # Проверяем, загружался ли ранее проект с таким же ключом дедупликации
    existing_proj = (
        await db.execute(select(Project).where(Project.lineage_dedup_key == pdf_sha256[:64]))
    ).scalar_one_or_none()

    job_id = str(uuid.uuid4())
    revision_id = uuid.uuid4()

    if existing_proj is not None:
        project_id = existing_proj.id
        existing_proj.status = ProjectStatus.PROCESSING.value
    else:
        project_id = uuid.uuid4()
        new_proj = Project(
            id=project_id,
            lineage_dedup_key=pdf_sha256[:64],
            title=(title or file.filename or "Uploaded University Thesis")[:290],
            status=ProjectStatus.PROCESSING.value,
        )
        db.add(new_proj)

    await db.commit()

    lock_payload = orjson.dumps(
        {
            "job_id": job_id,
            "project_id": str(project_id),
            "revision_id": str(revision_id),
        }
    )
    await r_state.set(lock_key, lock_payload, nx=True, ex=180)

    queue_depth = await get_ingest_queue_depth()
    est_wait = round(queue_depth * 3.5, 1) if queue_depth > 30 else 0.0

    await publish_job_stream_event(
        job_id=job_id,
        event_type="queued",
        step=0,
        percent=5,
        title="PDF accepted into Pre-Defense X-Ray Queue (%PDF-1.x signature verified)...",
        payload={
            "project_id": str(project_id),
            "revision_id": str(revision_id),
            "pdf_sha256": pdf_sha256,
            "queue_depth": queue_depth,
            "estimated_wait_seconds": est_wait,
        },
    )

    celery_app.send_task(
        "workers.worker_parser.parse_pdf_task",
        kwargs={
            "job_id": job_id,
            "project_id_str": str(project_id),
            "revision_id_str": str(revision_id),
            "pdf_path_str": saved_pdf_path,
            "pdf_sha256": pdf_sha256,
            "explicit_repo_url": repo_url.strip() if repo_url else None,
            "explicit_title": title.strip() if title else None,
        },
        queue="q_parser",
    )

    return {
        "job_id": job_id,
        "project_id": str(project_id),
        "revision_id": str(revision_id),
        "status": "QUEUED",
        "estimated_wait_seconds": est_wait,
        "sse_url": f"/api/v1/jobs/{job_id}/stream",
    }


# ==============================================================================
# ЭНДПОИНТ [2]: GET /api/v1/jobs/{job_id}/stream (REDIS STREAMS SSE + POLLING)
# ==============================================================================
@app.get("/api/v1/jobs/{job_id}/stream")
async def stream_or_poll_job_progress(
    request: Request,
    job_id: str,
    fallback: str | None = Query(default=None, description="Передайте 'poll' для JSON Short-Polling"),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> Any:
    """
    Универсальный эндпоинт отслеживания прогресса обработки диплома (Шаги 1..6):
    1) Если `fallback=poll` — возвращает всю накопленную историю из Redis Stream через XRANGE как JSON
       (автоматический фоллбэк, если корпоративный файрвол вуза блокирует потоки SSE).
    2) По умолчанию — открывает Server-Sent Events (SSE) стрим через XREAD BLOCK с позиции Last-Event-ID
       (или `0-0`), гарантируя нулевую потерю событий при реконнекте.
    """
    await enforce_rate_limit(request, "Zone_Read", capacity=100.0, refill_per_sec=5.0)
    r_state = get_redis_state()
    stream_key = f"stream:job:{job_id}"

    if fallback == "poll":
        entries = await r_state.xrange(stream_key, min="-", max="+")
        events_list: list[dict[str, Any]] = []
        latest_status = "PROCESSING"
        for entry_id, fields in entries:
            raw_data = fields.get(b"data")
            if raw_data:
                parsed = orjson.loads(raw_data)
                parsed["stream_entry_id"] = entry_id.decode("utf-8") if isinstance(entry_id, bytes) else str(entry_id)
                events_list.append(parsed)
                if parsed.get("event") in ("completed", "error"):
                    latest_status = parsed["event"].upper()
        return {
            "job_id": job_id,
            "status": latest_status,
            "events": events_list,
        }

    async def _sse_event_generator() -> AsyncGenerator[dict[str, str], None]:
        cursor = last_event_id if last_event_id else "0-0"
        idle_ticks = 0

        while idle_ticks < 90:
            if await request.is_disconnected():
                break

            streams = await r_state.xread({stream_key: cursor}, count=20, block=2000)
            if not streams:
                idle_ticks += 1
                yield {"event": "ping", "data": '{"keepalive": true}'}
                continue

            idle_ticks = 0
            for _, messages in streams:
                for entry_id_bytes, fields in messages:
                    entry_id_str = (
                        entry_id_bytes.decode("utf-8")
                        if isinstance(entry_id_bytes, bytes)
                        else str(entry_id_bytes)
                    )
                    cursor = entry_id_str
                    ev_bytes = fields.get(b"event", b"progress")
                    ev_name = ev_bytes.decode("utf-8") if isinstance(ev_bytes, bytes) else str(ev_bytes)
                    data_bytes = fields.get(b"data", b"{}")
                    data_str = data_bytes.decode("utf-8") if isinstance(data_bytes, bytes) else str(data_bytes)

                    yield {
                        "id": entry_id_str,
                        "event": ev_name,
                        "data": data_str,
                    }
                    if ev_name in ("completed", "error"):
                        return

    return EventSourceResponse(_sse_event_generator())


# ==============================================================================
# ЭНДПОИНТ [3]: GET /api/v1/projects (КАТАЛОГ БИРЖИ + ДЕТАЛЬНОЕ ДОСЬЕ И ГЕНЕАЛОГИЯ)
# ==============================================================================
@app.get("/api/v1/projects")
@app.get("/api/v1/projects/{project_id_path}")
async def list_or_get_project(
    request: Request,
    project_id_path: uuid.UUID | None = None,
    project_id: uuid.UUID | None = Query(default=None),
    modality: str | None = Query(default=None),
    language: str | None = Query(default=None),
    department: str | None = Query(default=None),
    domain_profile: str | None = Query(default=None),
    archetype: str | None = Query(default=None),
    min_score: float = Query(default=0.0),
    has_dataset: bool = Query(default=False),
    q: str | None = Query(default=None, description="Поисковый запрос по названию / автору / теме"),
    limit: int = Query(default=60, ge=1, le=250),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """
    Универсальный эндпоинт чтения проектов:
    - Если передан `project_id` (в пути или query) — возвращает полное Рентген-досье проекта (`passport`),
      актуальные статусы бронирования задач (`atomic_demand_items`) и рекурсивный граф поколений (`lineage_graph`).
    - Иначе — возвращает отфильтрованный массив проектов для «Биржи эстафеты» (Режим 2).
    """
    await enforce_rate_limit(request, "Zone_Read", capacity=100.0, refill_per_sec=5.0)
    target_id = project_id_path or project_id

    if target_id is not None:
        proj = (await db.execute(select(Project).where(Project.id == target_id))).scalar_one_or_none()
        if proj is None:
            raise HTTPException(status_code=404, detail="Проект не найден.")

        rev = (
            await db.execute(select(ProjectRevision).where(ProjectRevision.id == proj.current_revision_id))
        ).scalar_one_or_none()
        passport_data = (rev.passport_json if rev else {}) or {}

        demand_rows = list(
            (
                await db.execute(
                    select(AtomicDemandItem)
                    .where(AtomicDemandItem.project_id == proj.id)
                    .order_by(AtomicDemandItem.item_index.asc())
                )
            ).scalars().all()
        )
        supply_rows = list(
            (
                await db.execute(
                    select(AtomicSupplyItem)
                    .where(AtomicSupplyItem.project_id == proj.id)
                    .order_by(AtomicSupplyItem.item_index.asc())
                )
            ).scalars().all()
        )
        lineage_graph = await get_project_lineage_graph(db, proj.id)

        return {
            "project_id": str(proj.id),
            "title": proj.title,
            "year": proj.publication_year,
            "department": proj.department,
            "author": proj.author_name,
            "supervisor": proj.supervisor_name,
            "domain_profile": proj.domain_profile,
            "modality": proj.modality,
            "primary_language": proj.primary_language,
            "lifecycle_archetype": proj.lifecycle_archetype,
            "status": proj.status,
            "final_handover_score": float(proj.final_handover_score),
            "revision_number": rev.revision_number if rev else 1,
            "security_alert": rev.security_alert if rev else None,
            "plagiarism_alert": rev.plagiarism_alert if rev else None,
            "passport": passport_data,
            "atomic_demand_items": [
                {
                    "id": str(d.id),
                    "item_index": d.item_index,
                    "macro_category": d.macro_category,
                    "source_section": d.source_section,
                    "claim_status": d.claim_status,
                    "task_description": d.task_description,
                    "abstract_math_function": d.abstract_math_function,
                    "operating_envelope": d.operating_envelope,
                }
                for d in demand_rows
            ],
            "atomic_supply_items": [
                {
                    "id": str(s.id),
                    "item_index": s.item_index,
                    "asset_type": s.asset_type,
                    "domain_specific_text": s.domain_specific_text,
                    "abstract_math_function": s.abstract_math_function,
                    "operating_envelope": s.operating_envelope,
                    "effective_asset_score": float(s.effective_asset_score),
                }
                for s in supply_rows
            ],
            "lineage_graph": lineage_graph.model_dump(mode="json"),
        }

    # Каталог для Биржи эстафеты (Режим 2)
    stmt = (
        select(Project, ProjectRevision)
        .join(ProjectRevision, Project.current_revision_id == ProjectRevision.id)
        .where(
            Project.status == ProjectStatus.COMPLETED.value,
            Project.final_handover_score >= min_score,
        )
    )
    if modality and modality != "all":
        stmt = stmt.where(Project.modality == modality)
    if language and language != "all":
        stmt = stmt.where(Project.primary_language.ilike(f"%{language}%"))
    if department and department != "all":
        stmt = stmt.where(Project.department.ilike(f"%{department}%"))
    if domain_profile and domain_profile != "all":
        stmt = stmt.where(Project.domain_profile == domain_profile)
    if archetype and archetype != "all":
        stmt = stmt.where(Project.lifecycle_archetype == archetype)
    if has_dataset:
        stmt = stmt.where(ProjectRevision.raw_data_score >= 15)
    if q and q.strip():
        q_clean = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Project.title.ilike(q_clean),
                Project.author_name.ilike(q_clean),
                Project.department.ilike(q_clean),
            )
        )

    stmt = stmt.order_by(Project.final_handover_score.desc(), Project.updated_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).all()

    items_out: list[dict[str, Any]] = []
    for proj, rev in rows:
        p_json = rev.passport_json or {}
        supply_sec = p_json.get("supply_assets", {})
        demand_sec = p_json.get("demand_horizon", {})
        audit_sec = p_json.get("deep_harvest_audit", {})
        verif_sec = p_json.get("artifact_verification", {})
        scoring_sec = p_json.get("scoring", {})

        items_out.append(
            {
                "project_id": str(proj.id),
                "title": proj.title,
                "year": proj.publication_year,
                "department": proj.department,
                "author": proj.author_name,
                "supervisor": proj.supervisor_name,
                "domain_profile": proj.domain_profile,
                "modality": proj.modality,
                "primary_language": proj.primary_language,
                "lifecycle_archetype": proj.lifecycle_archetype,
                "is_pure_supply_donor": (proj.lifecycle_archetype == "GOLD_STANDARD_COMPLETED"),
                "final_handover_score": float(proj.final_handover_score),
                "scoring": scoring_sec,
                "artifact_verification": verif_sec,
                "supply_summary": {
                    "code_summary": supply_sec.get("code_summary", ""),
                    "data_summary": supply_sec.get("data_summary", ""),
                    "items_count": len(supply_sec.get("atomic_supply_items", [])),
                },
                "demand_summary": {
                    "macro_category": demand_sec.get("bottleneck_macro_category", ""),
                    "cluster_label": demand_sec.get("bottleneck_cluster_label", ""),
                    "tasks": demand_sec.get("atomic_demand_items", []),
                },
                "discarded_approaches": audit_sec.get("discarded_approaches", []),
                "gap_severity": rev.gap_severity,
                "security_alert": rev.security_alert,
                "plagiarism_alert": rev.plagiarism_alert,
            }
        )

    return {"total": len(items_out), "items": items_out}


# ==============================================================================
# ЭНДПОИНТ [4]: GET /api/v1/projects/{project_id}/synergy (АСИММЕТРИЧНЫЙ ПОИСК)
# ==============================================================================
@app.get("/api/v1/projects/{project_id}/synergy")
async def get_project_synergy_matches(
    request: Request,
    project_id: uuid.UUID,
    bounty_query: str | None = Query(
        default=None,
        description="Опциональный запрос от индустриального партнера (Corporate Bounty Matching)",
    ),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Возвращает карточки сшивания проектов (Synergy Bridge: Demand A -> Supply B)
    с расчетом калиброванной формулы S_{A<-B} и внешними рекомендациями HuggingFace Hub.
    Защищен механизмом SingleFlight от Cache Stampede.
    """
    await enforce_rate_limit(request, "Zone_External_Match", capacity=20.0, refill_per_sec=0.5)

    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if proj is None:
        raise HTTPException(status_code=404, detail="Проект не найден.")

    rev = (
        await db.execute(select(ProjectRevision).where(ProjectRevision.id == proj.current_revision_id))
    ).scalar_one_or_none()
    if rev is None or not rev.passport_json:
        raise HTTPException(status_code=404, detail="Паспорт ревизии не найден.")

    passport = CoreProjectSchema.model_validate(rev.passport_json)
    return await get_synergy_with_singleflight(
        db=db,
        project_id=project_id,
        passport=passport,
        bounty_query=bounty_query,
    )


# ==============================================================================
# ЭНДПОИНТ [5]: POST /api/v1/projects/{project_id}/claim (TAKE THE BATON)
# ==============================================================================
@app.post("/api/v1/projects/{project_id}/claim")
async def claim_relay_baton_endpoint(
    request: Request,
    project_id: uuid.UUID,
    body: TakeBatonRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Бронирует открытую задачу из Future Work за студентом младшего курса (Take the Baton)
    с пессимистичной блокировкой `FOR UPDATE NOWAIT` и подписанием контракта академического роялти.
    При конкурентном нажатии возвращает HTTP 409 Conflict.
    """
    await enforce_rate_limit(request, "Zone_External_Match", capacity=20.0, refill_per_sec=0.5)
    try:
        result = await claim_project_baton(db=db, parent_project_id=project_id, req=body)
        dean_l1_cache.clear()
        return result
    except ValueError as exc:
        msg = str(exc)
        if "CONFLICT_ALREADY_CLAIMED" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc


# ==============================================================================
# ЭНДПОИНТ [6]: POST /api/v1/projects/{project_id}/package (АВТО-УПАКОВЩИК)
# ==============================================================================
@app.post("/api/v1/projects/{project_id}/package")
async def generate_legacy_package_endpoint(
    request: Request,
    project_id: uuid.UUID,
    body: PackageGenerationRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Генерирует готовые файлы документации наследия:
    1) `HANDOVER_PASSPORT.md` (с красным щитом «Не повторять» и GitHub Issues)
    2) `CITATION.cff` (стандарт цитирования для GitHub/Zenodo)
    3) `synergy_merge_spec_md` (1-страничное ТЗ на объединение двух проектов разных кафедр)
    """
    await enforce_rate_limit(request, "Zone_External_Match", capacity=20.0, refill_per_sec=0.5)
    try:
        pkg = await generate_handover_package(db=db, project_id=project_id, req=body)
        return pkg.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ==============================================================================
# ЭНДПОИНТ [7]: GET /api/v1/analytics/bottlenecks (ДАШБОРД ДЕКАНАТА — РЕЖИМ 3)
# ==============================================================================
@app.get("/api/v1/analytics/bottlenecks")
async def get_dean_bottlenecks_analytics_endpoint(
    request: Request,
    year: int | None = Query(default=None),
    department: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Отдает данные для всех 4 виджетов Панели Управления R&D-Ресурсами Деканата (Режим 3).
    Кэшируется в L1 In-Process Memory Cache (`TTLCache`, 30 сек) — время отклика < 1 мс.
    """
    await enforce_rate_limit(request, "Zone_Read", capacity=100.0, refill_per_sec=5.0)
    cache_key = f"dean:{year or 'all'}:{department or 'all'}"
    if cache_key in dean_l1_cache:
        return dean_l1_cache[cache_key]

    dto = await get_dean_analytics_dashboard(
        db=db,
        year_filter=year,
        department_filter=department,
    )
    payload = dto.model_dump(mode="json")
    dean_l1_cache[cache_key] = payload
    return payload


# ==============================================================================
# ЭНДПОИНТ [8]: POST /api/v1/analytics/export-topics (ДЕЙСТВИЯ ДЕКАНАТА 1-CLICK)
# ==============================================================================
@app.post("/api/v1/analytics/export-topics")
async def dean_action_and_export_endpoint(
    request: Request,
    body: DeanActionRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Выполняет прямые управленческие действия Деканата / Заведующего кафедрой:
    - `export_vkr_bank`: 1-Click экспорт выбранных проектов в утвержденный банк тем ВКР 2026/2027;
    - `export_grant_justification`: формирование заявки на целевую закупку / грант по кластеру тупиков;
    - `approve_domain`: одобрение внешнего домена кафедры из карантина;
    - `trigger_reclustering`: принудительный пересчет кластеров HDBSCAN.
    """
    await enforce_rate_limit(request, "Zone_External_Match", capacity=20.0, refill_per_sec=0.5)
    res = await execute_dean_action(db=db, req=body)
    dean_l1_cache.clear()
    return res

