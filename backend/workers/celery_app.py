"""
[10] Конфигурация Celery 5.4, маршрутизация 5 выделенных очередей (q_parser, q_probe,
q_auditor, q_synergy, q_cron), персистентный мост asyncio для пулов asyncpg/Redis/Qdrant,
контроль Backpressure (LLEN > 30) и обработчик карантина сбоев Dead Letter Queue (DLQ).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Coroutine, TypeVar

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from config_and_db import (
    db_session_context,
    get_redis_state,
    publish_job_stream_event,
    settings,
)
from models_and_schemas import FailedJobDLQ, Project, ProjectStatus

logger = logging.getLogger("horizon.celery")

T = TypeVar("T")

# ==============================================================================
# 1. ПЕРСИСТЕНТНЫЙ ЦИКЛ СОБЫТИЙ ASYNCIO НА ПРОЦЕСС ВОРКЕРА (БЕЗ ЗАКРЫТИЯ ПУЛОВ)
# ==============================================================================
_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_loop_thread: threading.Thread | None = None
_worker_loop_pid: int | None = None
_loop_lock = threading.Lock()


def _start_background_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def get_worker_event_loop() -> asyncio.AbstractEventLoop:
    """
    Возвращает единый долгоживущий цикл событий asyncio для текущего OS-процесса (с учетом fork в prefork).
    Все потоки воркера отправляют корутины через run_coroutine_threadsafe, поэтому пул asyncpg,
    клиенты Redis и gRPC-сокеты Qdrant всегда привязаны к одному активному циклу.
    """
    global _worker_loop, _worker_loop_thread, _worker_loop_pid
    current_pid = os.getpid()
    if _worker_loop is None or _worker_loop_pid != current_pid or _worker_loop.is_closed():
        with _loop_lock:
            if _worker_loop is None or _worker_loop_pid != current_pid or _worker_loop.is_closed():
                _worker_loop = asyncio.new_event_loop()
                _worker_loop_pid = current_pid
                _worker_loop_thread = threading.Thread(
                    target=_start_background_loop,
                    args=(_worker_loop,),
                    name=f"horizon-async-loop-{current_pid}",
                    daemon=True,
                )
                _worker_loop_thread.start()
    return _worker_loop


def run_async(coro: Coroutine[Any, Any, T], timeout: float = 180.0) -> T:
    """Исполняет асинхронную корутину внутри персистентного цикла воркера."""
    loop = get_worker_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


# ==============================================================================
# 2. ИНИЦИАЛИЗАЦИЯ CELERY И 5 ИЗОЛИРОВАННЫХ ОЧЕРЕДЕЙ REDIS (DB=0)
# ==============================================================================
celery_app = Celery(
    "horizon_relay",
    broker=settings.REDIS_STATE_URL,
    backend=settings.REDIS_STATE_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=7200,
    broker_connection_retry_on_startup=True,
    task_queues=(
        Queue("q_parser", routing_key="q_parser"),
        Queue("q_probe", routing_key="q_probe"),
        Queue("q_auditor", routing_key="q_auditor"),
        Queue("q_synergy", routing_key="q_synergy"),
        Queue("q_cron", routing_key="q_cron"),
    ),
    task_default_queue="q_parser",
    task_routes={
        "workers.worker_parser.parse_pdf_task": {"queue": "q_parser", "routing_key": "q_parser"},
        "workers.worker_probe.probe_repo_task": {"queue": "q_probe", "routing_key": "q_probe"},
        "workers.worker_auditor.map_single_chapter_task": {"queue": "q_auditor", "routing_key": "q_auditor"},
        "workers.worker_auditor.reduce_and_score_task": {"queue": "q_auditor", "routing_key": "q_auditor"},
        "workers.worker_synergy.index_synergy_task": {"queue": "q_synergy", "routing_key": "q_synergy"},
        "workers.worker_cron.reconcile_outbox_events_task": {"queue": "q_cron", "routing_key": "q_cron"},
        "workers.worker_cron.retry_deferred_github_probes_task": {"queue": "q_cron", "routing_key": "q_cron"},
        "workers.worker_cron.nightly_hdbscan_and_decay_task": {"queue": "q_cron", "routing_key": "q_cron"},
    },
    beat_schedule={
        "outbox-reconciler-every-15s": {
            "task": "workers.worker_cron.reconcile_outbox_events_task",
            "schedule": 15.0,
            "options": {"queue": "q_cron"},
        },
        "deferred-github-probe-every-15m": {
            "task": "workers.worker_cron.retry_deferred_github_probes_task",
            "schedule": 900.0,
            "options": {"queue": "q_cron"},
        },
        "nightly-hdbscan-and-decay-03am": {
            "task": "workers.worker_cron.nightly_hdbscan_and_decay_task",
            "schedule": crontab(hour=3, minute=0),
            "options": {"queue": "q_cron"},
        },
    },
)


# ==============================================================================
# 3. КОНТРОЛЬ BACKPRESSURE И ЗАПИСЬ СБОЕВ В DEAD LETTER QUEUE (DLQ)
# ==============================================================================
async def get_ingest_queue_depth() -> int:
    """Возвращает суммарную длину очередей парсинга и аудита в Redis для детекции Backpressure (>30)."""
    r = get_redis_state()
    q1 = await r.llen("q_parser")
    q2 = await r.llen("q_auditor")
    return int(q1 or 0) + int(q2 or 0)


async def handle_pipeline_failure_dlq(
    job_id: str,
    project_id_str: str | None,
    error: Exception,
    stage_title: str,
) -> None:
    """
    Переводит поврежденный проект в статус QUARANTINE, сохраняет диагностику в таблицу
    failed_jobs_dlq и Redis Stream `horizon:dlq:ingest`, и отправляет клиенту SSE-событие `error`.
    """
    tb_str = traceback.format_exc()
    err_type = type(error).__name__
    err_msg = str(error)

    logger.error("Pipeline failure on job=%s stage=%s: %s", job_id, stage_title, err_msg)

    try:
        r = get_redis_state()
        await r.xadd(
            "horizon:dlq:ingest",
            {
                "job_id": job_id,
                "project_id": project_id_str or "",
                "stage": stage_title,
                "error_type": err_type,
                "error_message": err_msg[:500],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            maxlen=500,
            approximate=True,
        )

        async with db_session_context() as db:
            proj_uuid = uuid.UUID(project_id_str) if project_id_str else None
            dlq_row = FailedJobDLQ(
                job_id=job_id,
                project_id=proj_uuid,
                error_type=err_type,
                error_message=err_msg[:1000],
                traceback_text=tb_str[:4000],
            )
            db.add(dlq_row)

            if proj_uuid is not None:
                from sqlalchemy import select

                proj = (await db.execute(select(Project).where(Project.id == proj_uuid))).scalar_one_or_none()
                if proj is not None:
                    proj.status = ProjectStatus.QUARANTINE.value
            await db.commit()
    except Exception as db_exc:
        logger.warning("Failed to record DLQ entry: %s", db_exc)

    await publish_job_stream_event(
        job_id=job_id,
        event_type="error",
        step=0,
        percent=100,
        title=f"Pipeline failed at '{stage_title}': {err_msg[:180]}",
        payload={
            "status": "QUARANTINE",
            "error_type": err_type,
            "diagnostics": err_msg,
        },
    )

