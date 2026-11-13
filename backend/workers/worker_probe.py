"""
[12] Воркер №2 (q_probe, --pool=threads --concurrency=8, mem_limit=384m).
Отвечает за:
1. Неблокирующий сетевой опрос GitHub / GitLab / HuggingFace / Zenodo / OSF по API.
2. Защиту от SSRF, ротацию пула токенов GitHub PAT и потоковую проверку .ipynb через ijson.
3. Сохранение результата в таблицу artifact_probes и возврат DTO в Celery Chord.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from config_and_db import db_session_context, publish_job_stream_event
from core.artifact_probe import probe_project_artifacts
from models_and_schemas import ArtifactVerificationDTO
from workers.celery_app import celery_app, run_async

logger = logging.getLogger("horizon.worker_probe")


async def _run_probe_async(
    job_id: str,
    project_id_str: str,
    revision_id_str: str,
    urls_from_text: list[str],
    explicit_repo_url: str | None,
    has_in_pdf_appendix: bool,
) -> dict[str, Any]:
    project_id = uuid.UUID(project_id_str)
    revision_id = uuid.UUID(revision_id_str)

    async with db_session_context() as db:
        probe_dto: ArtifactVerificationDTO = await probe_project_artifacts(
            db=db,
            urls_from_text=urls_from_text,
            explicit_repo_url=explicit_repo_url,
            project_id=project_id,
            revision_id=revision_id,
            has_in_pdf_appendix=has_in_pdf_appendix,
        )

    status_badge = probe_dto.probe_status.value
    await publish_job_stream_event(
        job_id=job_id,
        event_type="progress",
        step=2,
        percent=48,
        title=f"Step 2/6: Artifact Probe finished (status: {status_badge}, repo_alive: {probe_dto.repo_alive}).",
        payload={"artifact_verification": probe_dto.model_dump(mode="json")},
    )

    return {
        "task_kind": "artifact_probe",
        "probe_dto": probe_dto.model_dump(mode="json"),
    }


@celery_app.task(name="workers.worker_probe.probe_repo_task", bind=True)
def probe_repo_task(
    self: Any,
    job_id: str,
    project_id_str: str,
    revision_id_str: str,
    urls_from_text: list[str],
    explicit_repo_url: str | None = None,
    has_in_pdf_appendix: bool = False,
) -> dict[str, Any]:
    """Выполняет проверку репозитория и внешних датасетов параллельно с Map-Scan глав."""
    try:
        return run_async(
            _run_probe_async(
                job_id=job_id,
                project_id_str=project_id_str,
                revision_id_str=revision_id_str,
                urls_from_text=urls_from_text,
                explicit_repo_url=explicit_repo_url,
                has_in_pdf_appendix=has_in_pdf_appendix,
            ),
            timeout=25.0,
        )
    except Exception as exc:
        logger.warning("Probe task graceful fallback on job=%s: %s", job_id, exc)
        fallback_dto = ArtifactVerificationDTO(
            repo_url=explicit_repo_url,
            has_data_artifact=has_in_pdf_appendix,
            diagnostics={"fallback_error": str(exc)},
        )
        return {
            "task_kind": "artifact_probe",
            "probe_dto": fallback_dto.model_dump(mode="json"),
        }

