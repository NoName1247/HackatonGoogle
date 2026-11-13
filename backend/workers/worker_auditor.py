"""
[13] Воркер №3 (q_auditor, --pool=threads --concurrency=8, mem_limit=512m).
Отвечает за:
1. Выполнение параллельных задач `map_single_chapter_task` для незакэшированных подглав середины диплома.
2. Сборку результатов в колбэке Chord `reduce_and_score_task`:
   - Вызов `run_cross_check_reducer` (Zero-Trust Extractor v2.1: Выводы против Середины + 3 вопроса ГАК + ТРИЗ);
   - Вызов детерминированной формулы `calculate_deterministic_handover_score` (Модуль 4);
   - Атомарное сохранение паспорта, ревизии, атомарных элементов SUPPLY/DEMAND и записи `OutboxEvent` в PostgreSQL;
   - Передачу эстафеты в `worker_synergy` (очередь `q_synergy`).
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from config_and_db import (
    db_session_context,
    deterministic_uuid5,
    publish_job_stream_event,
)
from core.auditor_and_scorer import (
    calculate_deterministic_handover_score,
    extract_single_chapter_with_cache,
    run_cross_check_reducer,
)
from core.harvester import resolve_lineage_and_detect_rewrite
from models_and_schemas import (
    ArtifactProbe,
    ArtifactVerificationDTO,
    AtomicDemandItem,
    AtomicSupplyItem,
    ChapterChunkDTO,
    ChapterMeatSchema,
    CoreProjectSchema,
    HarvestedDocumentDTO,
    LineageInfoSchema,
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

logger = logging.getLogger("horizon.worker_auditor")


async def _map_single_chapter_async(
    revision_id_str: str,
    chunk_dict: dict[str, Any],
    global_context_header: str,
) -> dict[str, Any]:
    revision_id = uuid.UUID(revision_id_str)
    chunk_dto = ChapterChunkDTO.model_validate(chunk_dict)
    async with db_session_context() as db:
        meat_schema = await extract_single_chapter_with_cache(
            db=db,
            revision_id=revision_id,
            chunk=chunk_dto,
            global_context_header=global_context_header,
        )
    return {
        "task_kind": "chapter_meat",
        "chunk_index": chunk_dto.chunk_index,
        "meat": meat_schema.model_dump(mode="json"),
    }


@celery_app.task(name="workers.worker_auditor.map_single_chapter_task", bind=True)
def map_single_chapter_task(
    self: Any,
    job_id: str,
    revision_id_str: str,
    chunk_dict: dict[str, Any],
    global_context_header: str,
) -> dict[str, Any]:
    """Траление одной подглавы из зоны CORE_ENG (часть заголовка Celery Chord)."""
    return run_async(
        _map_single_chapter_async(
            revision_id_str=revision_id_str,
            chunk_dict=chunk_dict,
            global_context_header=global_context_header,
        ),
        timeout=45.0,
    )


async def _reduce_score_and_persist_async(
    chord_results: list[dict[str, Any]],
    job_id: str,
    project_id_str: str,
    revision_id_str: str,
    harvest_dict: dict[str, Any],
    cached_meats_by_idx: dict[str, Any],
) -> dict[str, Any]:
    harvest = HarvestedDocumentDTO.model_validate(harvest_dict)
    probe_dto = ArtifactVerificationDTO()
    meats_map: dict[int, ChapterMeatSchema] = {}

    for k_str, m_val in (cached_meats_by_idx or {}).items():
        meats_map[int(k_str)] = ChapterMeatSchema.model_validate(m_val)

    for item in chord_results or []:
        if not isinstance(item, dict):
            continue
        if item.get("task_kind") == "artifact_probe":
            probe_dto = ArtifactVerificationDTO.model_validate(item.get("probe_dto", {}))
        elif item.get("task_kind") == "chapter_meat":
            c_idx = int(item.get("chunk_index", 0))
            meats_map[c_idx] = ChapterMeatSchema.model_validate(item.get("meat", {}))

    ordered_meats = [meats_map[idx] for idx in sorted(meats_map.keys())]

    await publish_job_stream_event(
        job_id=job_id,
        event_type="progress",
        step=3,
        percent=65,
        title="Step 3/6: Cross-checking Conclusion Claims vs. Middle-Chapter Reality (Zero-Trust Extractor v2.1)...",
        payload={"middle_chapters_analyzed": len(ordered_meats)},
    )

    async with db_session_context() as db:
        # 1. Трехфакторная проверка дедупликации (черновик того же автора vs одноименная работа другого студента)
        matched_existing_proj, plagiarism_alert = await resolve_lineage_and_detect_rewrite(
            db=db,
            harvest=harvest,
            new_semantic_centroid=None,
        )

        target_project_id = uuid.UUID(project_id_str)
        revision_id = uuid.UUID(revision_id_str)

        if matched_existing_proj is not None and matched_existing_proj.id != target_project_id:
            # Переключаем ревизию на найденный проект того же автора (Черновик v2+) и удаляем временную заглушку
            temp_proj = (
                await db.execute(select(Project).where(Project.id == target_project_id))
            ).scalar_one_or_none()
            if temp_proj is not None and temp_proj.current_revision_id is None:
                await db.delete(temp_proj)
                await db.flush()
            project_obj = matched_existing_proj
            target_project_id = matched_existing_proj.id
            harvest.project_id = target_project_id
        else:
            project_obj = (
                await db.execute(select(Project).where(Project.id == target_project_id))
            ).scalar_one_or_none()

        # Вычисляем порядковый номер ревизии (1, 2, 3...)
        max_rev_res = await db.execute(
            select(func.max(ProjectRevision.revision_number)).where(
                ProjectRevision.project_id == target_project_id
            )
        )
        prev_max_rev = max_rev_res.scalar_one_or_none() or 0
        rev_number = int(prev_max_rev) + 1

        # 2. Запускаем Cross-Check Reducer (Модуль 3)
        extracted_llm = await run_cross_check_reducer(
            db=db,
            harvest=harvest,
            middle_extracts=ordered_meats,
            probe=probe_dto,
        )

        await publish_job_stream_event(
            job_id=job_id,
            event_type="progress",
            step=4,
            percent=82,
            title="Step 4/6: Computing deterministic Handover Score & exponential Time-Decay...",
            payload={"lifecycle_archetype": extracted_llm.lifecycle_archetype.value},
        )

        # 3. Запускаем Детерминированный Скорер (Модуль 4)
        scoring = calculate_deterministic_handover_score(
            extracted=extracted_llm,
            probe=probe_dto,
            middle_extracts=ordered_meats,
            has_structured_appendix=harvest.has_structured_appendix,
        )

        sec_alert_code = (
            harvest.security_alerts[0].alert_code
            if harvest.security_alerts
            else None
        )

        # Проставляем детерминированные item_id внутри паспорта
        for s_idx, s_item in enumerate(extracted_llm.supply_assets.atomic_supply_items):
            s_item.item_id = str(deterministic_uuid5("SUPPLY", revision_id, s_idx))
        for d_idx, d_item in enumerate(extracted_llm.demand_horizon.atomic_demand_items):
            d_item.item_id = str(deterministic_uuid5("DEMAND", revision_id, d_idx))

        full_passport = CoreProjectSchema(
            project_id=str(target_project_id),
            revision_id=str(revision_id),
            revision_number=rev_number,
            lifecycle_archetype=extracted_llm.lifecycle_archetype,
            security_alert=sec_alert_code,
            plagiarism_alert=plagiarism_alert,
            lineage=LineageInfoSchema(generation=1),
            meta=extracted_llm.meta,
            artifact_verification=probe_dto,
            deep_harvest_audit=extracted_llm.deep_harvest_audit,
            supply_assets=extracted_llm.supply_assets,
            demand_horizon=extracted_llm.demand_horizon,
            llm_audit_flags=extracted_llm.llm_audit_flags,
            scoring=scoring,
        )

        # 4. Атомарная транзакция в PostgreSQL: Project + ProjectRevision + Probe + Supply/Demand + OutboxEvent
        if project_obj is None:
            project_obj = Project(
                id=target_project_id,
                lineage_dedup_key=harvest.pdf_sha256[:64],
                title=extracted_llm.meta.title[:295],
                publication_year=extracted_llm.meta.year,
                department=extracted_llm.meta.department[:115],
                author_name=extracted_llm.meta.author[:145],
                supervisor_name=extracted_llm.meta.supervisor[:145],
                domain_profile=extracted_llm.meta.domain_profile.value,
                modality=extracted_llm.meta.modality.value,
                primary_language=extracted_llm.meta.primary_language[:30],
                lifecycle_archetype=extracted_llm.lifecycle_archetype.value,
                status=ProjectStatus.PROCESSING.value,
                final_handover_score=Decimal(str(scoring.final_handover_score)),
                minhash_signature=harvest.minhash_signature,
                hard_anchors_hash=harvest.hard_anchors_hash,
                hard_anchors_json=harvest.hard_anchors,
            )
            db.add(project_obj)
            await db.flush()
        else:
            project_obj.title = extracted_llm.meta.title[:295]
            project_obj.publication_year = extracted_llm.meta.year
            project_obj.department = extracted_llm.meta.department[:115]
            project_obj.author_name = extracted_llm.meta.author[:145]
            project_obj.supervisor_name = extracted_llm.meta.supervisor[:145]
            project_obj.domain_profile = extracted_llm.meta.domain_profile.value
            project_obj.modality = extracted_llm.meta.modality.value
            project_obj.primary_language = extracted_llm.meta.primary_language[:30]
            project_obj.lifecycle_archetype = extracted_llm.lifecycle_archetype.value
            project_obj.final_handover_score = Decimal(str(scoring.final_handover_score))
            project_obj.minhash_signature = harvest.minhash_signature
            project_obj.hard_anchors_hash = harvest.hard_anchors_hash
            project_obj.hard_anchors_json = harvest.hard_anchors

        rev_row = ProjectRevision(
            id=revision_id,
            project_id=target_project_id,
            revision_number=rev_number,
            pdf_sha256=harvest.pdf_sha256,
            pdf_blob_path=harvest.pdf_blob_path,
            markdown_zst_path=harvest.markdown_zst_path,
            passport_json=full_passport.model_dump(mode="json"),
            llm_audit_flags=extracted_llm.llm_audit_flags.model_dump(mode="json"),
            raw_code_score=scoring.raw_code_score,
            raw_data_score=scoring.raw_data_score,
            validity_score=scoring.validity_score,
            horizon_component_score=scoring.roadmap_or_maturity_score,
            time_decay_code=Decimal(str(scoring.time_decay_code)),
            time_decay_data=Decimal(str(scoring.time_decay_data)),
            gap_severity=extracted_llm.deep_harvest_audit.reality_vs_conclusion_gap.gap_severity.value,
            security_alert=sec_alert_code,
            plagiarism_alert=plagiarism_alert,
        )
        db.add(rev_row)
        await db.flush()

        probe_row = ArtifactProbe(
            id=uuid.uuid4(),
            revision_id=revision_id,
            repo_url=probe_dto.repo_url,
            latest_commit_sha=probe_dto.latest_commit_sha,
            repo_alive=probe_dto.repo_alive,
            has_dependencies=probe_dto.has_dependencies,
            has_clean_paths=probe_dto.has_clean_paths,
            has_data_artifact=probe_dto.has_data_artifact,
            has_license=probe_dto.has_license,
            probe_status=probe_dto.probe_status.value,
            probe_diagnostics_json=probe_dto.diagnostics,
        )
        db.add(probe_row)

        eff_asset = Decimal(
            str(
                round(
                    scoring.raw_code_score * scoring.time_decay_code
                    + scoring.raw_data_score * scoring.time_decay_data,
                    2,
                )
            )
        )

        for idx, s_item in enumerate(extracted_llm.supply_assets.atomic_supply_items):
            s_uuid = deterministic_uuid5("SUPPLY", revision_id, idx)
            db.add(
                AtomicSupplyItem(
                    id=s_uuid,
                    project_id=target_project_id,
                    revision_id=revision_id,
                    item_index=idx,
                    asset_type=s_item.asset_type[:30],
                    domain_specific_text=s_item.domain_specific_text,
                    abstract_math_function=s_item.abstract_math_function,
                    operating_envelope=s_item.operating_envelope.model_dump(mode="json"),
                    effective_asset_score=eff_asset,
                )
            )

        for idx, d_item in enumerate(extracted_llm.demand_horizon.atomic_demand_items):
            d_uuid = deterministic_uuid5("DEMAND", revision_id, idx)
            db.add(
                AtomicDemandItem(
                    id=d_uuid,
                    project_id=target_project_id,
                    revision_id=revision_id,
                    item_index=idx,
                    macro_category=d_item.macro_category.value,
                    source_section=d_item.source[:60],
                    claim_status=d_item.claim_status.value,
                    task_description=d_item.task_description,
                    abstract_math_function=d_item.abstract_math_function,
                    operating_envelope=d_item.operating_envelope.model_dump(mode="json"),
                )
            )

        outbox_row = OutboxEvent(
            aggregate_id=target_project_id,
            event_type="SYNC_REVISION_VECTORS",
            payload={
                "job_id": job_id,
                "project_id": str(target_project_id),
                "revision_id": str(revision_id),
                "revision_number": rev_number,
                "middle_extracts": [m.model_dump(mode="json") for m in ordered_meats],
            },
            status="PENDING",
        )
        db.add(outbox_row)

        project_obj.current_revision_id = revision_id
        await db.commit()
        outbox_id = outbox_row.id

    return {
        "outbox_id": outbox_id,
        "project_id": str(target_project_id),
        "revision_id": str(revision_id),
        "revision_number": rev_number,
        "middle_extracts": [m.model_dump(mode="json") for m in ordered_meats],
    }


@celery_app.task(name="workers.worker_auditor.reduce_and_score_task", bind=True)
def reduce_and_score_task(
    self: Any,
    chord_results: list[dict[str, Any]],
    job_id: str,
    project_id_str: str,
    revision_id_str: str,
    harvest_dict: dict[str, Any],
    cached_meats_by_idx: dict[str, Any],
) -> dict[str, Any]:
    """Колбэк Celery Chord: выполняет ИИ-аудит, считает Handover Score и ставит задачу в q_synergy."""
    try:
        res = run_async(
            _reduce_score_and_persist_async(
                chord_results=chord_results,
                job_id=job_id,
                project_id_str=project_id_str,
                revision_id_str=revision_id_str,
                harvest_dict=harvest_dict,
                cached_meats_by_idx=cached_meats_by_idx,
            ),
            timeout=90.0,
        )

        celery_app.send_task(
            "workers.worker_synergy.index_synergy_task",
            kwargs={
                "job_id": job_id,
                "project_id_str": res["project_id"],
                "revision_id_str": res["revision_id"],
                "revision_number": res["revision_number"],
                "outbox_id": res["outbox_id"],
                "middle_extracts_raw": res["middle_extracts"],
            },
            queue="q_synergy",
        )
        return {"status": "dispatched_to_synergy", "project_id": res["project_id"]}

    except Exception as exc:
        run_async(
            handle_pipeline_failure_dlq(
                job_id=job_id,
                project_id_str=project_id_str,
                error=exc,
                stage_title="AI Audit & Handover Score Calculation (Modules 3–4)",
            )
        )
        raise

