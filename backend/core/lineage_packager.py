"""
[9] Project Lineage Graph ('Git for Science') & Legacy Auto-Packager (English Edition).
Handles:
1. Recursive CTE traversal of thesis generations (WITH RECURSIVE lineage_graph ... CYCLE).
2. Pessimistic concurrency locking for task reservation (SELECT ... FOR UPDATE NOWAIT -> HTTP 409 Conflict).
3. Automated generation of HANDOVER_PASSPORT.md, CITATION.cff, and 1-page Synergy Merge Specification.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from jinja2 import Template
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from models_and_schemas import (
    AtomicDemandItem,
    AtomicSupplyItem,
    ClaimStatus,
    HandoverPackageDTO,
    LineageEdgeDTO,
    LineageGraphDTO,
    LineageNodeDTO,
    PackageGenerationRequest,
    Project,
    ProjectLineageEdge,
    ProjectRevision,
    RelayClaim,
    TakeBatonRequest,
)

logger = logging.getLogger("horizon.lineage")


# ==============================================================================
# 1. JINJA2 TEMPLATES FOR HANDOVER_PASSPORT.MD, CITATION.CFF & SYNERGY SPEC
# ==============================================================================
HANDOVER_PASSPORT_TEMPLATE = Template(
    """# 🧭 HORIZON RELAY — TECHNICAL HANDOVER PASSPORT

> **Project:** "{{ meta.title }}" (`{{ project_id }}`)
> **Department:** {{ meta.department }} | **Profile:** `{{ meta.domain_profile }}` | **Year:** {{ meta.year }}
> **Primary Author:** {{ meta.author }} | **Faculty Advisor:** {{ meta.supervisor }}
> **Handover Continuity Score:** **{{ scoring.final_handover_score }} / 100** (`{{ scoring.status }}`)

---

## 1. 📦 Verified Starter Kit (Supply Assets)
- **Curated Data & Empirical Corpus:** {{ supply.data_summary }}
- **Code & Methodology:** {{ supply.code_summary }}
- **Primary Stack / Tooling:** `{{ meta.primary_language }}` ({{ meta.frameworks | join(', ') }})
- **Repository / Archive URL:** {{ verif.repo_url or 'In-Document Validated Primary Tables & Appendices' }}
- **Automated Probe Verification:** `{{ verif.probe_status }}` (Repo Alive: `{{ verif.repo_alive }}`, Clean Paths: `{{ verif.has_clean_paths }}`, Data Artifact: `{{ verif.has_data_artifact }}`)

### Atomic Reusable Modules & Datasets:
{% for item in supply.atomic_supply_items %}
{{ loop.index }}. **[{{ item.asset_type | upper }}]** {{ item.domain_specific_text }}
   - *TRIZ Mathematical Function:* `{{ item.abstract_math_function }}`
   - *Operating Envelope & I/O:* `{{ item.operating_envelope.domain_env }}` (`{{ item.operating_envelope.io_signature }}`)
{% endfor %}

---

## 2. 🔍 Forensic Reality Audit (Middle Chapters vs. Conclusion)
- **Conclusion Claim:** "{{ audit.reality_vs_conclusion_gap.conclusion_claim }}"
- **Middle-Chapter Reality (Page {{ audit.reality_vs_conclusion_gap.source_page }}):** {{ audit.reality_vs_conclusion_gap.middle_chapter_reality }}
- **Discrepancy Severity:** `{{ audit.reality_vs_conclusion_gap.gap_severity }}`

---

## 3. ⚠️ Implicit Dead-End Shield (DO NOT REPEAT!)
The following approaches and hypotheses were already tested by the predecessor and failed:
{% if audit.discarded_approaches %}
{% for d in audit.discarded_approaches %}
- ❌ **{{ d.method }}** ({{ d.source_location }}): {{ d.failure_reason }}
{% endfor %}
{% else %}
- No failed experimental branches recorded in middle chapters.
{% endif %}

---

## 4. 🎯 Actionable R&D Issues for Next Generation (Validated Demand)
{% for task in demand.atomic_demand_items %}
### [ISSUE #{{ loop.index }}] {{ task.task_description }}
- **Bottleneck Macro-Category:** `{{ task.macro_category }}` (Source: {{ task.source }})
- **TRIZ Target Transformation:** `{{ task.abstract_math_function }}`
- **Claim Status:** `{{ task.claim_status }}`
{% endfor %}

---

## 5. 🤝 Academic Royalty & Citation Contract
Any thesis, paper, or grant building upon the data, calculation tables, or codebase of this project MUST cite the primary author (**{{ meta.author }}**) and faculty advisor (**{{ meta.supervisor }}**) according to the accompanying `CITATION.cff`.
"""
)

CITATION_CFF_TEMPLATE = Template(
    """cff-version: 1.2.0
message: "If you build upon the data, methodology, or code of this research in your thesis or paper, please cite the original author (Horizon Relay Academic Royalty Contract)."
title: "{{ meta.title }}"
date-released: "{{ meta.year }}-06-15"
version: "1.{{ revision_number }}.0"
license: "MIT"
repository-code: "{{ verif.repo_url or 'https://horizon-relay.univ.edu/projects/' ~ project_id }}"
keywords:
  - "{{ meta.domain_profile }}"
  - "{{ meta.modality }}"
  - "{{ meta.department }}"
authors:
  - family-names: "{{ meta.author }}"
    affiliation: "{{ meta.department }}"
    role: "Creator & Primary Author (Gen 1)"
  - family-names: "{{ meta.supervisor }}"
    affiliation: "{{ meta.department }}"
    role: "Academic Supervisor & Co-Author"
{% if follower_name %}
  - family-names: "{{ follower_name }}"
    affiliation: "{{ meta.department }}"
    role: "Relay Follower (Next Generation Developer)"
{% endif %}
"""
)

SYNERGY_MERGE_SPEC_TEMPLATE = Template(
    """# 🔗 CROSS-DEPARTMENTAL SYNERGY MERGE SPECIFICATION (R&D BRIDGE SPEC)

> **Target Academic Year:** 2026/2027 | **Assigned Relay Fellow:** {{ follower_name }}
> **Primary Project A (Consumer / Demand):** "{{ proj_a.title }}" ({{ proj_a.department }}, Author: {{ proj_a.author_name }})
> **Donor Project B (Provider / Supply):** "{{ proj_b.title }}" ({{ proj_b.department }}, Author: {{ proj_b.author_name }})

---

## 1. Cross-Departmental Synergy Rationale
1. **Unresolved Bottleneck in Project A (Demand):** {{ demand_text }}
   - *TRIZ Function Vector:* `{{ demand_math }}`
2. **Verified Reusable Asset from Project B (Supply):** {{ supply_text }}
   - *TRIZ Solution Vector:* `{{ supply_math }}`

## 2. Step-by-Step Integration Roadmap (Thesis Milestones)
1. **Milestone 1 (Months 1-2): Base Environment Deployment.**
   Clone and verify the primary dataset and empirical testbed of Project A ({{ passport_a.supply_assets.data_summary }}). Review the predecessor's "Dead-End Shield" (Chapter 3) to avoid already-tested negative branches.
2. **Milestone 2 (Months 3-5): Donor Module Integration.**
   Interface the verified module from the Department of {{ proj_b.department }} ({{ supply_text }}) to close the open bottleneck without reinventing the wheel from scratch.
3. **Milestone 3 (Months 6-8): End-to-End Validation & Boundary Testing.**
   Run benchmark evaluations comparing the joint system against the baseline performance of Project A (`Predecessor Handover Score: {{ proj_a.final_handover_score }}`).

## 3. Academic Royalty & Co-Authorship Protocol
- Faculty Advisor of Project A (**{{ proj_a.supervisor_name }}**) and Faculty Advisor of Project B (**{{ proj_b.supervisor_name }}**) shall be included as academic co-authors on any publication or patent resulting from this cross-departmental integration.
"""
)


# ==============================================================================
# 2. RECURSIVE GENERATIONS GRAPH ("GIT FOR SCIENCE": WITH RECURSIVE ... CYCLE)
# ==============================================================================
async def get_project_lineage_graph(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> LineageGraphDTO:
    recursive_sql = text(
        """
        WITH RECURSIVE lineage_graph AS (
            SELECT
                e.parent_project_id,
                e.child_project_id,
                e.inherited_asset_type,
                e.citation_contract_signed,
                1 AS depth
            FROM project_lineage_edges e
            WHERE e.parent_project_id = :pid OR e.child_project_id = :pid
            UNION
            SELECT
                e2.parent_project_id,
                e2.child_project_id,
                e2.inherited_asset_type,
                e2.citation_contract_signed,
                lg.depth + 1
            FROM project_lineage_edges e2
            INNER JOIN lineage_graph lg
                ON e2.parent_project_id = lg.child_project_id
                OR e2.child_project_id = lg.parent_project_id
            WHERE lg.depth < 10
        ) CYCLE parent_project_id, child_project_id SET is_cycle USING path
        SELECT DISTINCT
            parent_project_id,
            child_project_id,
            inherited_asset_type,
            citation_contract_signed
        FROM lineage_graph
        WHERE NOT is_cycle;
        """
    )

    edge_rows = (await db.execute(recursive_sql, {"pid": project_id})).all()

    involved_ids: set[uuid.UUID] = {project_id}
    edges_dto: list[LineageEdgeDTO] = []

    for r in edge_rows:
        p_uuid = uuid.UUID(str(r[0]))
        c_uuid = uuid.UUID(str(r[1]))
        involved_ids.add(p_uuid)
        involved_ids.add(c_uuid)
        edges_dto.append(
            LineageEdgeDTO(
                parent_project_id=str(p_uuid),
                child_project_id=str(c_uuid),
                inherited_asset_type=str(r[2] or "dataset"),
                citation_contract_signed=bool(r[3]),
            )
        )

    projs = list(
        (await db.execute(select(Project).where(Project.id.in_(involved_ids)))).scalars().all()
    )

    parent_map: dict[str, list[str]] = {}
    for e in edges_dto:
        parent_map.setdefault(e.child_project_id, []).append(e.parent_project_id)

    def _calc_gen(pid_str: str, visited: set[str]) -> int:
        if pid_str in visited or pid_str not in parent_map:
            return 1
        visited.add(pid_str)
        return 1 + max(_calc_gen(par, visited) for par in parent_map[pid_str])

    nodes_dto: list[LineageNodeDTO] = []
    for p in projs:
        p_str = str(p.id)
        gen_num = _calc_gen(p_str, set())
        nodes_dto.append(
            LineageNodeDTO(
                project_id=p_str,
                title=p.title,
                author=p.author_name,
                supervisor=p.supervisor_name,
                year=p.publication_year,
                department=p.department,
                final_handover_score=float(p.final_handover_score),
                lifecycle_archetype=p.lifecycle_archetype,
                generation=gen_num,
            )
        )

    nodes_dto.sort(key=lambda n: (n.generation, n.year))
    root_id = nodes_dto[0].project_id if nodes_dto else str(project_id)

    return LineageGraphDTO(
        root_project_id=root_id,
        nodes=nodes_dto,
        edges=edges_dto,
    )


# ==============================================================================
# 3. LEGACY AUTO-PACKAGER (GENERATE_HANDOVER_PACKAGE)
# ==============================================================================
async def generate_handover_package(
    db: AsyncSession,
    project_id: uuid.UUID,
    req: PackageGenerationRequest | None = None,
) -> HandoverPackageDTO:
    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if proj is None:
        raise ValueError(f"Project {project_id} not found")

    rev = (
        await db.execute(select(ProjectRevision).where(ProjectRevision.id == proj.current_revision_id))
    ).scalar_one_or_none()
    if rev is None:
        raise ValueError(f"Active revision for project {project_id} not found")

    passport = rev.passport_json or {}
    follower_name = req.follower_student_name if req else "Next-Gen R&D Fellow"

    handover_md = HANDOVER_PASSPORT_TEMPLATE.render(
        project_id=str(proj.id),
        meta=passport.get("meta", {}),
        scoring=passport.get("scoring", {}),
        supply=passport.get("supply_assets", {}),
        demand=passport.get("demand_horizon", {}),
        audit=passport.get("deep_harvest_audit", {}),
        verif=passport.get("artifact_verification", {}),
    )

    citation_cff = CITATION_CFF_TEMPLATE.render(
        project_id=str(proj.id),
        revision_number=rev.revision_number,
        meta=passport.get("meta", {}),
        verif=passport.get("artifact_verification", {}),
        follower_name=follower_name,
    )

    merge_spec_md: str | None = None
    if req and (req.donor_project_id or req.donor_supply_item_id):
        donor_proj: Project | None = None
        supply_text = "Verified module / dataset from partner department"
        supply_math = "Cross-domain validated transformation asset"

        if req.donor_supply_item_id:
            s_item = (
                await db.execute(select(AtomicSupplyItem).where(AtomicSupplyItem.id == req.donor_supply_item_id))
            ).scalar_one_or_none()
            if s_item:
                supply_text = s_item.domain_specific_text
                supply_math = s_item.abstract_math_function
                donor_proj = (
                    await db.execute(select(Project).where(Project.id == s_item.project_id))
                ).scalar_one_or_none()

        if donor_proj is None and req.donor_project_id:
            donor_proj = (
                await db.execute(select(Project).where(Project.id == req.donor_project_id))
            ).scalar_one_or_none()
            if donor_proj and donor_proj.current_revision_id:
                d_rev = (
                    await db.execute(
                        select(ProjectRevision).where(ProjectRevision.id == donor_proj.current_revision_id)
                    )
                ).scalar_one_or_none()
                if d_rev and d_rev.passport_json:
                    s_items = d_rev.passport_json.get("supply_assets", {}).get("atomic_supply_items", [])
                    if s_items:
                        supply_text = s_items[0].get("domain_specific_text", supply_text)
                        supply_math = s_items[0].get("abstract_math_function", supply_math)

        demand_items = passport.get("demand_horizon", {}).get("atomic_demand_items", [])
        demand_text = demand_items[0].get("task_description", "Technical bottleneck remediation") if demand_items else "Technical bottleneck remediation"
        demand_math = demand_items[0].get("abstract_math_function", "") if demand_items else ""

        if donor_proj is not None:
            merge_spec_md = SYNERGY_MERGE_SPEC_TEMPLATE.render(
                follower_name=follower_name,
                proj_a=proj,
                proj_b=donor_proj,
                passport_a=passport,
                demand_text=demand_text,
                demand_math=demand_math,
                supply_text=supply_text,
                supply_math=supply_math,
            )

    return HandoverPackageDTO(
        project_id=str(proj.id),
        handover_passport_md=handover_md,
        citation_cff=citation_cff,
        synergy_merge_spec_md=merge_spec_md,
    )


# ==============================================================================
# 4. TASK RESERVATION "TAKE THE BATON" WITH FOR UPDATE NOWAIT
# ==============================================================================
async def claim_project_baton(
    db: AsyncSession,
    parent_project_id: uuid.UUID,
    req: TakeBatonRequest,
) -> dict[str, Any]:
    try:
        stmt = (
            select(AtomicDemandItem)
            .where(
                AtomicDemandItem.id == req.demand_item_id,
                AtomicDemandItem.project_id == parent_project_id,
            )
            .with_for_update(nowait=True)
        )
        demand_item = (await db.execute(stmt)).scalar_one_or_none()
    except (OperationalError, DBAPIError) as exc:
        await db.rollback()
        raise ValueError("CONFLICT_ALREADY_CLAIMED: This task is currently being claimed by another researcher.") from exc

    if demand_item is None:
        raise ValueError("DEMAND_ITEM_NOT_FOUND: The specified task does not exist in this project.")

    if demand_item.claim_status in (ClaimStatus.ASSIGNED.value, ClaimStatus.COMPLETED.value):
        raise ValueError(f"CONFLICT_ALREADY_CLAIMED: Task already claimed (Status: {demand_item.claim_status}).")

    parent_proj = (
        await db.execute(select(Project).where(Project.id == parent_project_id))
    ).scalar_one_or_none()
    if parent_proj is None:
        raise ValueError("PARENT_PROJECT_NOT_FOUND")

    demand_item.claim_status = ClaimStatus.ASSIGNED.value

    new_project_id = uuid.uuid4()
    next_gen_title = (
        req.new_project_title
        if req.new_project_title and len(req.new_project_title.strip()) >= 5
        else f"{demand_item.task_description[:75]} (Successor to: {parent_proj.title[:65]})"
    )

    child_proj = Project(
        id=new_project_id,
        lineage_dedup_key=f"claim_{new_project_id.hex[:16]}",
        title=next_gen_title[:290],
        publication_year=datetime.now(timezone.utc).year + 1,
        department=parent_proj.department,
        author_name=req.follower_student_name,
        supervisor_name=req.approving_supervisor_name,
        domain_profile=parent_proj.domain_profile,
        modality=parent_proj.modality,
        primary_language=parent_proj.primary_language,
        lifecycle_archetype="RELAY_CANDIDATE",
        status="PROCESSING",
    )
    db.add(child_proj)

    edge_row = ProjectLineageEdge(
        parent_project_id=parent_project_id,
        child_project_id=new_project_id,
        inherited_asset_type="dataset",
        citation_contract_signed=req.accept_citation_contract,
    )
    db.add(edge_row)

    claim_record = RelayClaim(
        id=uuid.uuid4(),
        parent_project_id=parent_project_id,
        demand_item_id=req.demand_item_id,
        donor_supply_item_id=req.donor_supply_item_id,
        follower_student_name=req.follower_student_name,
        approving_supervisor_name=req.approving_supervisor_name,
        status="APPROVED_ACTIVE",
    )
    db.add(claim_record)

    await db.commit()

    pkg = await generate_handover_package(
        db=db,
        project_id=parent_project_id,
        req=PackageGenerationRequest(
            donor_project_id=None,
            donor_supply_item_id=req.donor_supply_item_id,
            demand_item_id=req.demand_item_id,
            follower_student_name=req.follower_student_name,
        ),
    )

    claim_record.generated_package_json = pkg.model_dump(mode="json")
    await db.commit()

    return {
        "status": "claimed",
        "claim_id": str(claim_record.id),
        "parent_project_id": str(parent_project_id),
        "new_child_project_id": str(new_project_id),
        "task_description": demand_item.task_description,
        "follower_student_name": req.follower_student_name,
        "academic_royalty_contract": {
            "citation_cff_ready": True,
            "handover_passport_generated": True,
            "synergy_merge_spec_ready": bool(pkg.synergy_merge_spec_md),
        },
        "package": pkg.model_dump(mode="json"),
    }
