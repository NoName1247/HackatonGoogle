"""
[15] Воркер №5 (q_cron, --pool=solo + Celery Beat, mem_limit=768m).
Отвечает за периодические фоновые задачи обслуживания системы:
1. `reconcile_outbox_events_task` (каждые 15 сек): гарантированная доставка векторов в Qdrant
   по паттерну Transactional Outbox (SELECT ... FOR UPDATE SKIP LOCKED).
2. `retry_deferred_github_probes_task` (каждые 15 мин): допроверка репозиториев со статусом
   `DEFERRED_RETRY` (после сброса лимитов GitHub API) или `PENDING_DOMAIN` (после одобрения домена).
3. `nightly_hdbscan_and_decay_task` (раз в сутки / по кнопке декана): полный пересчет
   микро-кластеров UMAP + HDBSCAN и обновление коэффициентов старения активов Time-Decay.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from config_and_db import db_session_context, settings
from core.artifact_probe import probe_project_artifacts
from core.ontology_and_roi import run_offline_hdbscan_reclustering
from models_and_schemas import (
    ArtifactProbe,
    OutboxEvent,
    ProbeStatus,
    Project,
    ProjectRevision,
)
from workers.celery_app import celery_app, run_async

logger = logging.getLogger("horizon.worker_cron")


async def _reconcile_outbox_async() -> dict[str, Any]:
    """
    Читает повисшие записи в таблице outbox_events (status='PENDING') с блокировкой
    FOR UPDATE SKIP LOCKED и переотправляет их в очередь q_synergy.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=20)
    dispatched = 0

    async with db_session_context() as db:
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "PENDING",
                OutboxEvent.next_retry_at <= now,
                OutboxEvent.created_at <= cutoff,
            )
            .order_by(OutboxEvent.next_retry_at.asc(), OutboxEvent.id.asc())
            .limit(10)
            .with_for_update(skip_locked=True)
        )
        events = list((await db.execute(stmt)).scalars().all())
        for ev in events:
            if ev.retry_count >= 5:
                ev.status = "FAILED"
                continue

            payload = ev.payload or {}
            ev.retry_count += 1
            ev.next_retry_at = now + timedelta(seconds=30 * ev.retry_count)

            celery_app.send_task(
                "workers.worker_synergy.index_synergy_task",
                kwargs={
                    "job_id": payload.get("job_id", f"outbox_{ev.id}"),
                    "project_id_str": payload.get("project_id", str(ev.aggregate_id)),
                    "revision_id_str": payload.get("revision_id", ""),
                    "revision_number": int(payload.get("revision_number", 1)),
                    "outbox_id": ev.id,
                    "middle_extracts_raw": payload.get("middle_extracts", []),
                },
                queue="q_synergy",
            )
            dispatched += 1

        if events:
            await db.commit()

    return {"reconciled_count": dispatched}


async def _retry_deferred_probes_async() -> dict[str, Any]:
    """
    Повторно проверяет репозитории, попавшие под Rate-Limit GitHub API (DEFERRED_RETRY)
    или получившие одобрение кафедрального домена (PENDING_DOMAIN), и обновляет Handover Score.
    """
    updated_count = 0
    async with db_session_context() as db:
        stmt = (
            select(ArtifactProbe, ProjectRevision, Project)
            .join(ProjectRevision, ArtifactProbe.revision_id == ProjectRevision.id)
            .join(Project, ProjectRevision.project_id == Project.id)
            .where(
                ArtifactProbe.probe_status.in_(
                    [ProbeStatus.DEFERRED_RETRY.value, ProbeStatus.PENDING_DOMAIN.value]
                )
            )
            .limit(15)
        )
        rows = (await db.execute(stmt)).all()
        for probe_row, rev_row, proj_row in rows:
            if not probe_row.repo_url:
                continue
            new_dto = await probe_project_artifacts(
                db=db,
                urls_from_text=[probe_row.repo_url],
                explicit_repo_url=probe_row.repo_url,
                project_id=proj_row.id,
                revision_id=rev_row.id,
                has_in_pdf_appendix=bool(rev_row.llm_audit_flags.get("has_structured_appendix", False)),
            )
            if new_dto.probe_status == ProbeStatus.VERIFIED:
                probe_row.repo_alive = new_dto.repo_alive
                probe_row.has_dependencies = new_dto.has_dependencies
                probe_row.has_clean_paths = new_dto.has_clean_paths
                probe_row.has_data_artifact = new_dto.has_data_artifact
                probe_row.has_license = new_dto.has_license
                probe_row.probe_status = new_dto.probe_status.value
                probe_row.probe_diagnostics_json = new_dto.diagnostics

                # Пересчитываем Code_Score и итоговый балл после верификации репозитория
                raw_code = (
                    (10 if new_dto.repo_alive else 0)
                    + (10 if (new_dto.has_dependencies and new_dto.has_clean_paths) else 5 if (new_dto.has_dependencies or new_dto.has_clean_paths) else 0)
                    + (5 if new_dto.has_license else 0)
                )
                rev_row.raw_code_score = raw_code
                new_total = round(
                    raw_code * float(rev_row.time_decay_code)
                    + float(rev_row.raw_data_score) * float(rev_row.time_decay_data)
                    + float(rev_row.validity_score)
                    + float(rev_row.horizon_component_score),
                    2,
                )
                proj_row.final_handover_score = Decimal(str(min(100.0, new_total)))
                if rev_row.passport_json:
                    p_json = dict(rev_row.passport_json)
                    p_json["artifact_verification"] = new_dto.model_dump(mode="json")
                    if "scoring" in p_json:
                        p_json["scoring"]["raw_code_score"] = raw_code
                        p_json["scoring"]["final_handover_score"] = float(proj_row.final_handover_score)
                    rev_row.passport_json = p_json
                updated_count += 1

        if updated_count > 0:
            await db.commit()

    return {"reprobed_verified_count": updated_count}


async def _nightly_hdbscan_and_decay_async() -> dict[str, Any]:
    """Пересчитывает кластеры HDBSCAN и обновляет экспоненциальное затухание Time-Decay."""
    async with db_session_context() as db:
        cluster_stats = await run_offline_hdbscan_reclustering(db)

        stmt = select(Project, ProjectRevision).join(
            ProjectRevision, Project.current_revision_id == ProjectRevision.id
        )
        rows = (await db.execute(stmt)).all()
        now_year = settings.CURRENT_ACADEMIC_YEAR
        for proj, rev in rows:
            dt = max(0.0, float(now_year - (proj.publication_year or now_year)))
            is_soft = bool((rev.llm_audit_flags or {}).get("has_software_code", True))
            lam_c = 0.45 if is_soft else 0.15
            decay_c = round(math.exp(-lam_c * dt), 3)
            decay_d = round(math.exp(-0.10 * dt), 3)
            rev.time_decay_code = Decimal(str(decay_c))
            rev.time_decay_data = Decimal(str(decay_d))
            recalc = round(
                float(rev.raw_code_score) * decay_c
                + float(rev.raw_data_score) * decay_d
                + float(rev.validity_score)
                + float(rev.horizon_component_score),
                2,
            )
            proj.final_handover_score = Decimal(str(min(100.0, recalc)))

        await db.commit()
    return {"status": "ok", "clusters": cluster_stats, "projects_decay_updated": len(rows)}


@celery_app.task(name="workers.worker_cron.reconcile_outbox_events_task")
def reconcile_outbox_events_task() -> dict[str, Any]:
    return run_async(_reconcile_outbox_async(), timeout=30.0)


@celery_app.task(name="workers.worker_cron.retry_deferred_github_probes_task")
def retry_deferred_github_probes_task() -> dict[str, Any]:
    return run_async(_retry_deferred_probes_async(), timeout=60.0)


@celery_app.task(name="workers.worker_cron.nightly_hdbscan_and_decay_task")
def nightly_hdbscan_and_decay_task() -> dict[str, Any]:
    return run_async(_nightly_hdbscan_and_decay_async(), timeout=180.0)

