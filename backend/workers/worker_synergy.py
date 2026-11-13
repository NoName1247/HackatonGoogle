"""
[14] Воркер №4 (q_synergy, --pool=threads --concurrency=4, ONNX_SEMAPHORE=2, mem_limit=2560m).
ЕДИНСТВЕННЫЙ воркер в системе, который импортирует `core.synergy_engine` и держит в памяти
локальные модели `BAAI/bge-m3`, `Qdrant/bm25` и `BAAI/bge-reranker-v2-m3`.
Отвечает за:
1. Генерацию Dense+Sparse векторов и идемпотентный Upsert в 3 коллекции Qdrant.
2. Поиск пересечений с прошлыми дипломами вуза (Prior Art Radar).
3. Онлайн-привязку узких мест (Demand) к микро-кластерам тупиков Деканата (Модуль 6).
4. Закрытие транзакционного события `OutboxEvent = 'PROCESSED'` и отправку финального SSE `completed`.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select

from config_and_db import db_session_context, publish_job_stream_event
from core.ontology_and_roi import assign_demand_to_cluster_online
from core.synergy_engine import compute_prior_art_radar, index_project_vectors
from models_and_schemas import (
    ChapterMeatSchema,
    CoreProjectSchema,
    OutboxEvent,
    Project,
    ProjectRevision,
    ProjectStatus,
)
from workers.celery_app import (
    celery_app,
    handle_pipeline_failure_dlq,
    run_async,
)

logger = logging.getLogger("horizon.worker_synergy")


async def _index_synergy_and_complete_async(
    job_id: str,
    project_id_str: str,
    revision_id_str: str,
    revision_number: int,
    outbox_id: int | None,
    middle_extracts_raw: list[dict[str, Any]],
) -> dict[str, Any]:
    project_id = uuid.UUID(project_id_str)
    revision_id = uuid.UUID(revision_id_str)

    await publish_job_stream_event(
        job_id=job_id,
        event_type="progress",
        step=5,
        percent=92,
        title="Step 5/6: Local ONNX embedding (bge-m3 + BM25), Qdrant indexing & Prior Art Radar...",
        payload={"project_id": project_id_str, "revision_number": revision_number},
    )

    middle_extracts = [ChapterMeatSchema.model_validate(m) for m in (middle_extracts_raw or [])]

    async with db_session_context() as db:
        proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
        rev = (
            await db.execute(select(ProjectRevision).where(ProjectRevision.id == revision_id))
        ).scalar_one_or_none()
        if proj is None or rev is None:
            raise ValueError(f"Project {project_id_str} or Revision {revision_id_str} missing in DB.")

        passport = CoreProjectSchema.model_validate(rev.passport_json)

        # 1. Индексируем векторы в 3 коллекции Qdrant и получаем смысловой центроид документа
        centroid_vec, demand_vecs = await index_project_vectors(
            project_id=project_id,
            revision_id=revision_id,
            revision_number=revision_number,
            passport=passport,
            middle_extracts=middle_extracts,
        )

        # 2. Вычисляем Радар внутривузовских аналогов (Prior Art Radar)
        prior_art_refs = await compute_prior_art_radar(
            project_id=project_id,
            passport=passport,
        )
        passport.deep_harvest_audit.prior_art_radar.similar_past_projects = prior_art_refs

        # 3. Онлайн-привязка узких мест (Demand) к микро-кластерам тупиков Деканата
        for d_uuid, macro_cat, d_vec in demand_vecs:
            await assign_demand_to_cluster_online(
                db=db,
                demand_item_id=d_uuid,
                macro_category=macro_cat,
                dense_vec=d_vec,
            )

        # 4. Сохраняем смысловой центроид на карточке проекта, обновляем паспорт и закрываем OutboxEvent
        proj.semantic_centroid_fp32 = centroid_vec.tobytes()
        proj.status = ProjectStatus.COMPLETED.value
        rev.passport_json = passport.model_dump(mode="json")

        if outbox_id is not None:
            ob_row = (
                await db.execute(select(OutboxEvent).where(OutboxEvent.id == outbox_id))
            ).scalar_one_or_none()
            if ob_row is not None:
                ob_row.status = "PROCESSED"

        await db.commit()
        final_passport_dict = rev.passport_json

    await publish_job_stream_event(
        job_id=job_id,
        event_type="completed",
        step=6,
        percent=100,
        title="Step 6/6: COMPLETED! Forensic X-Ray Dossier & Asymmetric Synergy vectors ready.",
        payload={
            "project_id": project_id_str,
            "revision_id": revision_id_str,
            "revision_number": revision_number,
            "passport": final_passport_dict,
        },
    )

    return {"status": "completed", "project_id": project_id_str}


@celery_app.task(name="workers.worker_synergy.index_synergy_task", bind=True, max_retries=3)
def index_synergy_task(
    self: Any,
    job_id: str,
    project_id_str: str,
    revision_id_str: str,
    revision_number: int = 1,
    outbox_id: int | None = None,
    middle_extracts_raw: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Финальный шаг пайплайна: генерация эмбеддингов ONNX, запись в Qdrant и закрытие Outbox."""
    try:
        return run_async(
            _index_synergy_and_complete_async(
                job_id=job_id,
                project_id_str=project_id_str,
                revision_id_str=revision_id_str,
                revision_number=revision_number,
                outbox_id=outbox_id,
                middle_extracts_raw=middle_extracts_raw or [],
            ),
            timeout=120.0,
        )
    except Exception as exc:
        run_async(
            handle_pipeline_failure_dlq(
                job_id=job_id,
                project_id_str=project_id_str,
                error=exc,
                stage_title="ONNX Vectorization & Qdrant Indexing (Module 5)",
            )
        )
        raise

