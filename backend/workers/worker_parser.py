"""
[11] Воркер №1 (q_parser, --pool=prefork --concurrency=2, max_tasks_per_child=50).
Отвечает за:
1. CPU-парсинг PDF через PyMuPDF4LLM, межстраничное сшивание таблиц и санитайзер белого текста.
2. Селективный вызов локального RapidOCR для страниц со сканами (с отключением второстепенного OCR при Backpressure).
3. Предварительную проверку SHA-256 кэша глав в PostgreSQL: в Celery Chord ставятся задачи Map-Scan
   ТОЛЬКО для тех подглав, которых еще нет в кэше!
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from celery import chord
from sqlalchemy import select

from config_and_db import (
    db_session_context,
    get_redis_cache,
    publish_job_stream_event,
)
from core.harvester import parse_and_zone_pdf
from models_and_schemas import ChapterExtractionCache, ChapterMeatSchema
from workers.celery_app import (
    celery_app,
    get_ingest_queue_depth,
    handle_pipeline_failure_dlq,
    run_async,
)

logger = logging.getLogger("horizon.worker_parser")


async def _parse_and_prepare_chord_async(
    job_id: str,
    project_id_str: str,
    revision_id_str: str,
    pdf_path_str: str,
    pdf_sha256: str,
    explicit_repo_url: str | None,
    explicit_title: str | None,
) -> dict[str, Any]:
    project_id = uuid.UUID(project_id_str)
    revision_id = uuid.UUID(revision_id_str)
    pdf_path = Path(pdf_path_str)

    queue_depth = await get_ingest_queue_depth()
    disable_secondary_ocr = queue_depth > 30

    await publish_job_stream_event(
        job_id=job_id,
        event_type="progress",
        step=1,
        percent=18,
        title="Step 1/6: Full PDF parsing, cross-page table stitching & visual security scan...",
        payload={"queue_depth": queue_depth, "backpressure_mode": disable_secondary_ocr},
    )

    harvest_dto = parse_and_zone_pdf(
        project_id=project_id,
        revision_id=revision_id,
        pdf_path=pdf_path,
        pdf_sha256=pdf_sha256,
        explicit_title=explicit_title,
        disable_secondary_ocr=disable_secondary_ocr,
    )

    # Проверяем, какие из нарезанных подглав середины (CORE_ENG) уже лежат в SHA-256 кэше PostgreSQL
    cached_meats_by_idx: dict[int, dict[str, Any]] = {}
    uncached_chunks_dicts: list[dict[str, Any]] = []

    if harvest_dto.core_chunks:
        cache_keys = [c.cache_key for c in harvest_dto.core_chunks]
        async with db_session_context() as db:
            stmt = select(ChapterExtractionCache).where(
                ChapterExtractionCache.cache_key.in_(cache_keys)
            )
            rows = list((await db.execute(stmt)).scalars().all())
            by_key = {r.cache_key: r.extracted_meat_json for r in rows}

        r_cache = get_redis_cache()
        for ch in harvest_dto.core_chunks:
            if ch.cache_key in by_key:
                validated_meat = ChapterMeatSchema.model_validate(by_key[ch.cache_key])
                cached_meats_by_idx[ch.chunk_index] = validated_meat.model_dump(mode="json")
            else:
                uncached_chunks_dicts.append(ch.model_dump(mode="json"))

    cache_hits = len(cached_meats_by_idx)
    total_chunks = len(harvest_dto.core_chunks)

    await publish_job_stream_event(
        job_id=job_id,
        event_type="progress",
        step=2,
        percent=35,
        title=(
            f"Step 2/6: Structural zoning complete ({harvest_dto.total_pages} pages, "
            f"chapter cache hits: {cache_hits}/{total_chunks}). Launching parallel Map-Scan & Artifact Probe..."
        ),
        payload={
            "total_pages": harvest_dto.total_pages,
            "ocr_pages": harvest_dto.ocr_pages_count,
            "chapter_cache_hits": cache_hits,
            "total_core_chunks": total_chunks,
            "detected_profile": harvest_dto.detected_domain_profile.value,
            "security_alerts_count": len(harvest_dto.security_alerts),
        },
    )

    return {
        "harvest": harvest_dto.model_dump(mode="json"),
        "cached_meats_by_idx": cached_meats_by_idx,
        "uncached_chunks": uncached_chunks_dicts,
        "explicit_repo_url": explicit_repo_url,
    }


@celery_app.task(name="workers.worker_parser.parse_pdf_task", bind=True, max_retries=1)
def parse_pdf_task(
    self: Any,
    job_id: str,
    project_id_str: str,
    revision_id_str: str,
    pdf_path_str: str,
    pdf_sha256: str,
    explicit_repo_url: str | None = None,
    explicit_title: str | None = None,
) -> dict[str, Any]:
    """
    Точка входа конвейера: парсит PDF и запускает параллельный Celery Chord:
    header = [probe_repo_task (q_probe)] + [map_single_chapter_task (q_auditor) для незакэшированных глав]
    body   = reduce_and_score_task (q_auditor)
    """
    try:
        prepared = run_async(
            _parse_and_prepare_chord_async(
                job_id=job_id,
                project_id_str=project_id_str,
                revision_id_str=revision_id_str,
                pdf_path_str=pdf_path_str,
                pdf_sha256=pdf_sha256,
                explicit_repo_url=explicit_repo_url,
                explicit_title=explicit_title,
            ),
            timeout=90.0,
        )

        harvest_dict = prepared["harvest"]
        cached_meats = prepared["cached_meats_by_idx"]
        uncached_chunks = prepared["uncached_chunks"]

        # Формируем параллельную шапку Chord: 1 задача в q_probe + K задач в q_auditor
        header_signatures = [
            celery_app.signature(
                "workers.worker_probe.probe_repo_task",
                kwargs={
                    "job_id": job_id,
                    "project_id_str": project_id_str,
                    "revision_id_str": revision_id_str,
                    "urls_from_text": harvest_dict.get("extracted_urls", []),
                    "explicit_repo_url": explicit_repo_url,
                    "has_in_pdf_appendix": bool(harvest_dict.get("has_structured_appendix", False)),
                },
                queue="q_probe",
            )
        ]

        for ch_dict in uncached_chunks:
            header_signatures.append(
                celery_app.signature(
                    "workers.worker_auditor.map_single_chapter_task",
                    kwargs={
                        "job_id": job_id,
                        "revision_id_str": revision_id_str,
                        "chunk_dict": ch_dict,
                        "global_context_header": harvest_dict.get("global_context_header", ""),
                    },
                    queue="q_auditor",
                )
            )

        callback_sig = celery_app.signature(
            "workers.worker_auditor.reduce_and_score_task",
            kwargs={
                "job_id": job_id,
                "project_id_str": project_id_str,
                "revision_id_str": revision_id_str,
                "harvest_dict": harvest_dict,
                "cached_meats_by_idx": cached_meats,
            },
            queue="q_auditor",
        )

        chord(header_signatures)(callback_sig)
        return {"status": "chord_dispatched", "job_id": job_id, "uncached_tasks": len(uncached_chunks)}

    except Exception as exc:
        run_async(
            handle_pipeline_failure_dlq(
                job_id=job_id,
                project_id_str=project_id_str,
                error=exc,
                stage_title="PDF Parsing & Security Scan (Module 1)",
            )
        )
        raise

