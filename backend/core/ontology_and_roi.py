"""
[8] Module 6 — Hierarchical Bottleneck Ontology & Dean's Office ROI Engine (English Edition).
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config_and_db import FinOpsBudgetTracker, get_async_qdrant, settings
from models_and_schemas import (
    AtomicDemandItem,
    BottleneckCluster,
    BottleneckMacroCategory,
    ClusterNodeDTO,
    DeanActionRequest,
    DeanAnalyticsResponseDTO,
    DomainModerationQueue,
    GoldenReserveBubbleDTO,
    LifecycleArchetype,
    MacroCategoryTreeDTO,
    Project,
    ProjectLineageEdge,
    ProjectRevision,
    ProjectStatus,
)

logger = logging.getLogger("horizon.ontology")

MACRO_ROI_TEMPLATES: dict[str, tuple[str, str]] = {
    BottleneckMacroCategory.COMPUTE_AND_HARDWARE.value: (
        "Targeted procurement of shared laboratory testbed / University GPU cluster quota allocation",
        "Unlocks parallel experimental execution across multiple departments without hardware duplication",
    ),
    BottleneckMacroCategory.DATA_SCARCITY_AND_ANNOTATION.value: (
        "Inter-departmental data annotation grant / Clinical & industrial data-sharing agreement",
        "Creates a long-lived university data asset (>5 yr half-life, lambda=0.10) across 3 thesis generations",
    ),
    BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS.value: (
        "Cross-faculty synergy pairing with Applied Math, Signal Processing & Radiophysics departments",
        "Reuses validated mathematical filters and optimization modules internally at $0.00 cost",
    ),
    BottleneckMacroCategory.SYSTEM_INTEGRATION_AND_PROD.value: (
        "Standardized containerization & Hardware-in-the-Loop (HIL) pre-defense integration testbed",
        "Advances prototypes from TRL 2-3 to industrial pilot readiness (TRL 5-6)",
    ),
    BottleneckMacroCategory.LEGAL_PRIVACY_AND_ACCESS.value: (
        "Partner with School of Law to deploy standardized k-anonymity / HIPAA / GDPR compliance kits",
        "Eliminates regulatory blockers for clinical, financial, and enterprise datasets",
    ),
    BottleneckMacroCategory.DOMAIN_VALIDATION.value: (
        "Establish cross-disciplinary domain review boards (clinicians, economists, engineers, legal experts)",
        "Verifies domain adequacy and statistical validity prior to thesis defense",
    ),
    BottleneckMacroCategory.SCOPE_OVERRUN_AND_UNFINISHED.value: (
        "Direct relay of unfinished modules and mock stubs to Junior/Sophomore R&D practicum cohorts",
        "Requires $0.00 capital expenditure from Dean's Office — resolved via student relay",
    ),
}


async def assign_demand_to_cluster_online(
    db: AsyncSession,
    demand_item_id: uuid.UUID,
    macro_category: str,
    dense_vec: np.ndarray,
    similarity_threshold: float = 0.78,
) -> uuid.UUID | None:
    stmt = select(BottleneckCluster).where(BottleneckCluster.macro_category == macro_category)
    clusters = list((await db.execute(stmt)).scalars().all())

    best_cluster: BottleneckCluster | None = None
    best_sim = -1.0
    vec_norm = float(np.linalg.norm(dense_vec)) or 1.0

    for cl in clusters:
        if not cl.medoid_vector_fp32:
            continue
        medoid = np.frombuffer(cl.medoid_vector_fp32, dtype=np.float32)
        if medoid.shape != dense_vec.shape:
            continue
        med_norm = float(np.linalg.norm(medoid)) or 1.0
        cos_sim = float(np.dot(dense_vec, medoid) / (vec_norm * med_norm))
        if cos_sim > best_sim:
            best_sim = cos_sim
            best_cluster = cl

    demand_row = (
        await db.execute(select(AtomicDemandItem).where(AtomicDemandItem.id == demand_item_id))
    ).scalar_one_or_none()

    if best_cluster is not None and best_sim >= similarity_threshold:
        if demand_row is not None:
            demand_row.cluster_id = best_cluster.id
        best_cluster.affected_projects_count = max(1, best_cluster.affected_projects_count + 1)
        await db.commit()
        return best_cluster.id

    return None


def _synthesize_cluster_label(macro_category: str, descriptions: list[str]) -> str:
    if not descriptions:
        return f"Systemic Bottleneck: {macro_category}"
    sorted_desc = sorted(descriptions, key=lambda s: abs(len(s) - 75))
    exemplar = sorted_desc[0].strip().rstrip(".")
    if len(exemplar) > 110:
        exemplar = exemplar[:107] + "..."
    return exemplar


async def run_offline_hdbscan_reclustering(db: AsyncSession) -> dict[str, Any]:
    qdrant = get_async_qdrant()
    stmt = (
        select(AtomicDemandItem, Project)
        .join(Project, AtomicDemandItem.project_id == Project.id)
        .where(Project.status == ProjectStatus.COMPLETED.value)
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return {"status": "empty", "clusters_updated": 0}

    point_ids = [str(d_item.id) for d_item, _ in rows]
    qdrant_points = await qdrant.retrieve(
        collection_name="demand_vectors",
        ids=point_ids,
        with_vectors=["dense"],
        with_payload=False,
    )
    vec_by_id: dict[str, np.ndarray] = {}
    for pt in qdrant_points:
        raw_v = pt.vector.get("dense") if isinstance(pt.vector, dict) else pt.vector
        if raw_v:
            vec_by_id[str(pt.id)] = np.asarray(raw_v, dtype=np.float32)

    by_macro: dict[str, list[tuple[AtomicDemandItem, Project, np.ndarray]]] = defaultdict(list)
    for d_item, proj in rows:
        vec = vec_by_id.get(str(d_item.id))
        if vec is not None:
            by_macro[d_item.macro_category].append((d_item, proj, vec))

    old_clusters = list((await db.execute(select(BottleneckCluster))).scalars().all())
    for oc in old_clusters:
        await db.delete(oc)
    await db.flush()

    total_created_clusters = 0
    total_emerging_noise = 0

    for macro_cat, items_list in by_macro.items():
        n_items = len(items_list)
        if n_items == 0:
            continue

        matrix = np.vstack([it[2] for it in items_list])
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        norm_matrix = matrix / norms

        labels = np.full(n_items, -1, dtype=int)

        if n_items >= 6:
            try:
                from sklearn.cluster import HDBSCAN

                clusterer = HDBSCAN(
                    min_cluster_size=3,
                    min_samples=2,
                    metric="euclidean",
                )
                labels = clusterer.fit_predict(norm_matrix)
            except Exception as exc:
                logger.warning("HDBSCAN fallback to cosine threshold clustering: %s", exc)

        unassigned_indices = [i for i, lbl in enumerate(labels) if lbl == -1]
        next_cluster_id = int(labels.max()) + 1 if len(labels) > 0 else 0

        visited_unassigned: set[int] = set()
        for idx_i in unassigned_indices:
            if idx_i in visited_unassigned:
                continue
            vec_i = norm_matrix[idx_i]
            sims = np.dot(norm_matrix[unassigned_indices], vec_i)
            neighbors = [
                unassigned_indices[pos]
                for pos, s_val in enumerate(sims)
                if s_val >= 0.55 and unassigned_indices[pos] not in visited_unassigned
            ]
            min_group = 2 if n_items < 15 else 3
            if len(neighbors) >= min_group:
                for n_idx in neighbors:
                    labels[n_idx] = next_cluster_id
                    visited_unassigned.add(n_idx)
                next_cluster_id += 1

        grouped_indices: dict[int, list[int]] = defaultdict(list)
        for i, lbl in enumerate(labels):
            grouped_indices[int(lbl)].append(i)

        for lbl, member_idxs in grouped_indices.items():
            if lbl == -1:
                for m_idx in member_idxs:
                    items_list[m_idx][0].cluster_id = None
                    total_emerging_noise += 1
                continue

            sub_vecs = norm_matrix[member_idxs]
            centroid = np.mean(sub_vecs, axis=0)
            c_norm = float(np.linalg.norm(centroid)) or 1.0
            centroid = centroid / c_norm

            medoid_local_idx = int(np.argmax(np.dot(sub_vecs, centroid)))
            medoid_vec = norm_matrix[member_idxs[medoid_local_idx]].astype(np.float32)

            member_demands = [items_list[i][0] for i in member_idxs]
            member_projects = [items_list[i][1] for i in member_idxs]

            unique_proj_ids = {str(p.id) for p in member_projects}
            unique_depts = sorted({p.department for p in member_projects if p.department})
            unique_supervisors = sorted({p.supervisor_name for p in member_projects if p.supervisor_name})
            descriptions = [d.task_description for d in member_demands]

            cluster_label = _synthesize_cluster_label(macro_cat, descriptions)
            action_tpl, roi_tpl = MACRO_ROI_TEMPLATES.get(
                macro_cat,
                ("Targeted inter-departmental grant & resource allocation", "Unlocks blocked research"),
            )

            new_cluster = BottleneckCluster(
                id=uuid.uuid4(),
                macro_category=macro_cat,
                cluster_label=cluster_label,
                affected_projects_count=len(unique_proj_ids),
                affected_departments_count=max(1, len(unique_depts)),
                medoid_vector_fp32=medoid_vec.tobytes(),
                roi_recommendation_json={
                    "recommended_action": action_tpl,
                    "estimated_unlock_roi": f"1 targeted intervention unblocks {len(unique_proj_ids)} theses across {max(1, len(unique_depts))} depts ({roi_tpl})",
                    "departments": unique_depts,
                    "supervisors": unique_supervisors[:10],
                    "project_ids": sorted(unique_proj_ids),
                    "project_titles": [p.title for p in member_projects[:15]],
                },
            )
            db.add(new_cluster)
            await db.flush()

            for d_obj in member_demands:
                d_obj.cluster_id = new_cluster.id

            total_created_clusters += 1

    await db.commit()
    return {
        "status": "completed",
        "clusters_created": total_created_clusters,
        "emerging_noise_buffered": total_emerging_noise,
    }


async def get_dean_analytics_dashboard(
    db: AsyncSession,
    year_filter: int | None = None,
    department_filter: str | None = None,
) -> DeanAnalyticsResponseDTO:
    proj_stmt = select(Project, ProjectRevision).join(
        ProjectRevision, Project.current_revision_id == ProjectRevision.id
    ).where(Project.status == ProjectStatus.COMPLETED.value)

    if year_filter:
        proj_stmt = proj_stmt.where(Project.publication_year == year_filter)
    if department_filter and department_filter.strip():
        proj_stmt = proj_stmt.where(Project.department.ilike(f"%{department_filter.strip()}%"))

    proj_rows = (await db.execute(proj_stmt)).all()

    edges_res = await db.execute(select(ProjectLineageEdge.parent_project_id))
    followed_parent_ids = {str(r[0]) for r in edges_res.all()}

    golden_bubbles: list[GoldenReserveBubbleDTO] = []
    trl_showcase: list[GoldenReserveBubbleDTO] = []
    relay_candidates_count = 0
    gold_standard_count = 0

    for proj, rev in proj_rows:
        asset_val_x = round(
            float(rev.raw_code_score) * float(rev.time_decay_code)
            + float(rev.raw_data_score) * float(rev.time_decay_data),
            2,
        )
        horizon_y = float(rev.horizon_component_score)
        is_gold = proj.lifecycle_archetype == LifecycleArchetype.GOLD_STANDARD_COMPLETED.value
        if is_gold:
            gold_standard_count += 1
        else:
            relay_candidates_count += 1

        bubble = GoldenReserveBubbleDTO(
            project_id=str(proj.id),
            title=proj.title,
            department=proj.department,
            author=proj.author_name,
            supervisor=proj.supervisor_name,
            year=proj.publication_year,
            domain_profile=proj.domain_profile,
            lifecycle_archetype=proj.lifecycle_archetype,
            asset_value_x=asset_val_x,
            horizon_score_y=horizon_y,
            final_handover_score=float(proj.final_handover_score),
            has_active_followers=(str(proj.id) in followed_parent_ids),
            is_pure_supply_donor=is_gold,
        )
        golden_bubbles.append(bubble)
        if is_gold or float(proj.final_handover_score) >= 90.0:
            trl_showcase.append(bubble)

    clusters_all = list((await db.execute(select(BottleneckCluster))).scalars().all())
    if not clusters_all and proj_rows:
        await run_offline_hdbscan_reclustering(db)
        clusters_all = list((await db.execute(select(BottleneckCluster))).scalars().all())

    unclassified_stmt = (
        select(AtomicDemandItem, Project)
        .join(Project, AtomicDemandItem.project_id == Project.id)
        .where(AtomicDemandItem.cluster_id.is_(None), Project.status == ProjectStatus.COMPLETED.value)
    )
    unclassified_rows = (await db.execute(unclassified_stmt)).all()

    clusters_by_macro: dict[str, list[ClusterNodeDTO]] = defaultdict(list)
    for cl in clusters_all:
        roi_info = cl.roi_recommendation_json or {}
        clusters_by_macro[cl.macro_category].append(
            ClusterNodeDTO(
                cluster_id=str(cl.id),
                cluster_label=cl.cluster_label,
                macro_category=cl.macro_category,
                affected_projects_count=cl.affected_projects_count,
                affected_departments_count=cl.affected_departments_count,
                departments_list=roi_info.get("departments", []),
                supervisors_list=roi_info.get("supervisors", []),
                project_ids=roi_info.get("project_ids", []),
                project_titles=roi_info.get("project_titles", []),
                estimated_unlock_roi=roi_info.get(
                    "estimated_unlock_roi",
                    f"Unblocks {cl.affected_projects_count} theses across {cl.affected_departments_count} depts.",
                ),
                recommended_action=roi_info.get("recommended_action", "Targeted cross-departmental support"),
            )
        )

    emerging_by_macro: dict[str, list[tuple[AtomicDemandItem, Project]]] = defaultdict(list)
    for d_item, proj in unclassified_rows:
        emerging_by_macro[d_item.macro_category].append((d_item, proj))

    for macro_cat, em_items in emerging_by_macro.items():
        p_ids = sorted({str(p.id) for _, p in em_items})
        depts = sorted({p.department for _, p in em_items})
        sups = sorted({p.supervisor_name for _, p in em_items})
        titles = [p.title for _, p in em_items[:10]]
        clusters_by_macro[macro_cat].append(
            ClusterNodeDTO(
                cluster_id=f"emerging_{macro_cat[:12].lower().replace(' ', '_')}",
                cluster_label=f"Emerging / Unclassified Bottlenecks ({len(p_ids)} theses buffered)",
                macro_category=macro_cat,
                affected_projects_count=len(p_ids),
                affected_departments_count=max(1, len(depts)),
                departments_list=depts,
                supervisors_list=sups,
                project_ids=p_ids,
                project_titles=titles,
                estimated_unlock_roi="Emerging trend buffer (auto-promotes to micro-cluster at >= 5 theses)",
                recommended_action="Monitor emerging R&D topics across faculty advisors",
            )
        )

    treemap_hierarchy: list[MacroCategoryTreeDTO] = []
    for cat_enum in BottleneckMacroCategory:
        cat_name = cat_enum.value
        cat_clusters = sorted(
            clusters_by_macro.get(cat_name, []),
            key=lambda c: c.affected_projects_count,
            reverse=True,
        )
        total_blocked = sum(c.affected_projects_count for c in cat_clusters)
        treemap_hierarchy.append(
            MacroCategoryTreeDTO(
                macro_category=cat_name,
                total_projects_blocked=total_blocked,
                clusters=cat_clusters,
            )
        )

    dom_rows = list(
        (
            await db.execute(
                select(DomainModerationQueue).where(DomainModerationQueue.status == "PENDING")
            )
        ).scalars().all()
    )
    pending_domains = [
        {
            "id": str(d.id),
            "domain": d.domain,
            "sample_url": d.sample_url,
            "project_id": str(d.project_id),
            "created_at": d.created_at.isoformat(),
        }
        for d in dom_rows
    ]

    daily_spend = await FinOpsBudgetTracker.get_today_spend_usd()

    return DeanAnalyticsResponseDTO(
        total_projects=len(proj_rows),
        relay_candidates_count=relay_candidates_count,
        gold_standard_trl_count=gold_standard_count,
        total_clusters_count=len(clusters_all),
        emerging_unclassified_count=len(unclassified_rows),
        daily_finops_spend_usd=daily_spend,
        daily_finops_budget_usd=settings.DAILY_LLM_BUDGET_USD,
        treemap_hierarchy=treemap_hierarchy,
        golden_reserve_matrix=golden_bubbles,
        trl_showcase_projects=trl_showcase,
        pending_domains=pending_domains,
    )


async def execute_dean_action(
    db: AsyncSession,
    req: DeanActionRequest,
) -> dict[str, Any]:
    if req.action_type == "approve_domain" and req.domain_id:
        dom = (
            await db.execute(select(DomainModerationQueue).where(DomainModerationQueue.id == req.domain_id))
        ).scalar_one_or_none()
        if dom is None:
            return {"status": "error", "message": "Domain not found in moderation queue."}
        dom.status = "APPROVED"
        dom.reviewed_by = req.reviewer_name
        await db.commit()
        return {
            "status": "approved",
            "domain": dom.domain,
            "message": f"Domain '{dom.domain}' added to the university allowlist by {req.reviewer_name}.",
        }

    if req.action_type == "trigger_reclustering":
        stats = await run_offline_hdbscan_reclustering(db)
        return {"status": "reclustered", "details": stats}

    if req.action_type == "export_grant_justification" and req.cluster_id:
        cl = (
            await db.execute(select(BottleneckCluster).where(BottleneckCluster.id == req.cluster_id))
        ).scalar_one_or_none()
        if cl is None:
            return {"status": "error", "message": "Cluster not found."}
        roi = cl.roi_recommendation_json or {}
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        md_doc = (
            f"# TARGETED INFRASTRUCTURE & GRANT PROCUREMENT JUSTIFICATION\n\n"
            f"**Date:** {now_str} | **Approved by:** {req.reviewer_name}\n"
            f"**Bottleneck Macro-Category:** `{cl.macro_category}`\n"
            f"**Systemic Bottleneck (HDBSCAN Cluster):** {cl.cluster_label}\n\n"
            f"---\n\n"
            f"## 1. Blast Radius & Bottleneck ROI Analysis\n"
            f"- **Blocked Theses & R&D Projects:** `{cl.affected_projects_count}` projects\n"
            f"- **Affected University Departments:** `{cl.affected_departments_count}` ({', '.join(roi.get('departments', []))})\n"
            f"- **Faculty Advisors Involved:** {', '.join(roi.get('supervisors', []))}\n"
            f"- **Estimated Unlock ROI:** {roi.get('estimated_unlock_roi', '')}\n\n"
            f"## 2. Recommended Executive Action\n"
            f"> {roi.get('recommended_action', '')}\n\n"
            f"## 3. Blocked Research Projects Unblocked by This Procurement\n"
        )
        for idx, t_title in enumerate(roi.get("project_titles", []), start=1):
            md_doc += f"{idx}. \"{t_title}\"\n"

        return {
            "status": "exported",
            "document_title": f"Grant & Procurement Memo — {cl.cluster_label[:60]}",
            "markdown_content": md_doc,
        }

    stmt = (
        select(Project, ProjectRevision)
        .join(ProjectRevision, Project.current_revision_id == ProjectRevision.id)
        .where(Project.status == ProjectStatus.COMPLETED.value)
    )
    if req.project_ids:
        stmt = stmt.where(Project.id.in_(req.project_ids))
    else:
        stmt = stmt.order_by(Project.final_handover_score.desc()).limit(20)

    rows = (await db.execute(stmt)).all()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        f"# APPROVED BANK OF RELAY THESIS TOPICS FOR {req.academic_year_target}",
        f"**Generated by Horizon Relay:** {now_str} | **Approved by:** {req.reviewer_name}",
        f"**Total Validated High-Potential Topics:** {len(rows)}",
        "",
        "---",
        "",
    ]

    for idx, (proj, rev) in enumerate(rows, start=1):
        passport = rev.passport_json or {}
        supply_sec = passport.get("supply_assets", {})
        demand_sec = passport.get("demand_horizon", {})
        audit_sec = passport.get("deep_harvest_audit", {})
        verif_sec = passport.get("artifact_verification", {})

        demand_tasks = demand_sec.get("atomic_demand_items", [])
        task_text = (
            demand_tasks[0].get("task_description")
            if demand_tasks
            else "Scale and validate the baseline prototype under production operating conditions"
        )
        discarded = audit_sec.get("discarded_approaches", [])
        dead_end_note = (
            f"{discarded[0].get('method')} ({discarded[0].get('failure_reason')})"
            if discarded
            else "No critical dead-end branches recorded"
        )

        lines.extend(
            [
                f"## Topic #{idx}. Continuation of: \"{proj.title}\"",
                f"- **Department:** {proj.department} | **Profile:** `{proj.domain_profile}`",
                f"- **Primary Asset Creator (Citation Royalty):** {proj.author_name} ({proj.publication_year})",
                f"- **Faculty Advisor / Consultant:** {proj.supervisor_name}",
                f"- **Asset Continuity Score (Handover Score):** `{proj.final_handover_score} / 100`",
                f"- **Verified Starter Kit (Supply):** {supply_sec.get('data_summary', '')} | {supply_sec.get('code_summary', '')}",
                f"- **Repository / Data Archive:** {verif_sec.get('repo_url') or 'University Department Validated Appendix Archive'}",
                f"- **Concrete R&D Specification for Incoming Student (Demand):** {task_text}",
                f"- **⚠️ Implicit Dead-End Shield (DO NOT REPEAT!):** {dead_end_note}",
                "",
            ]
        )

    return {
        "status": "exported",
        "exported_count": len(rows),
        "document_title": f"Approved Relay Thesis Topic Bank {req.academic_year_target}",
        "markdown_content": "\n".join(lines),
    }
