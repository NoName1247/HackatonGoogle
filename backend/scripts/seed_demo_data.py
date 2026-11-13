"""
[16] English Dataset Seeding Script for Google Hackathon Demo (200 University Projects + Live PDF).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config_and_db import (
    cas_storage,
    db_session_context,
    deterministic_uuid5,
    init_postgres_schema,
    init_qdrant_collections,
    settings,
)
from core.harvester import compute_minhash_signature, extract_universal_hard_anchors
from core.ontology_and_roi import run_offline_hdbscan_reclustering
from core.synergy_engine import index_project_vectors
from models_and_schemas import (
    ArtifactProbe,
    ArtifactVerificationDTO,
    AtomicDemandItem,
    AtomicDemandSchema,
    AtomicSupplyItem,
    AtomicSupplySchema,
    BottleneckMacroCategory,
    ChapterMeatSchema,
    ClaimStatus,
    CoreProjectSchema,
    DeepHarvestAuditSchema,
    DemandHorizonSectionSchema,
    DiscardedApproachExtract,
    DomainEnvType,
    DomainProfile,
    FutureWorkLinterItem,
    GapSeverity,
    HardSpecExtract,
    LifecycleArchetype,
    LineageInfoSchema,
    LLMAuditFlagsSchema,
    ModalityType,
    OperatingEnvelopeSchema,
    PriorArtProjectRef,
    PriorArtRadarSchema,
    ProbeStatus,
    Project,
    ProjectLineageEdge,
    ProjectMetaSchema,
    ProjectRevision,
    ProjectStatus,
    RealityVsConclusionGapSchema,
    ScoringBreakdownSchema,
    SupplyAssetsSectionSchema,
)

logger = logging.getLogger("horizon.seeder")


# ==============================================================================
# 1. LIVE DEMO PDF GENERATION
# ==============================================================================
def generate_sample_demo_pdf() -> Path:
    """Generates a multi-page English thesis PDF with tables, a hidden stub on p. 4, and Conclusion claims."""
    demo_dir = settings.BLOB_STORAGE_DIR / "demo_pdfs"
    demo_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = demo_dir / "demo_weld_xray_thesis.pdf"
    if pdf_path.exists():
        return pdf_path

    doc = fitz.open()
    pages_content = [
        (
            "INSTITUTE OF TECHNOLOGY & APPLIED ENGINEERING\n"
            "Department of Computer Vision & Nondestructive Testing\n\n"
            "MASTER'S THESIS\n"
            "Title: Automated Defect Segmentation in X-Ray Radiographs of Welded Joints\n\n"
            "Author: Elias Vance\n"
            "Supervisor: Prof. Arthur Pendelton\n"
            "Year: 2025\n\n"
            "# 1. Introduction\n"
            "Automated inspection of pipeline welds is critical for industrial safety. "
            "This thesis presents a real-time deep segmentation complex achieving 94% accuracy.\n"
            "Source code and weights: https://github.com/example/weld-xray-seg"
        ),
        (
            "# Chapter 1. Literature Review and Related Work\n\n"
            "Previous studies by Zhang et al. [14] collected 50,000 casting radiographs and reported 96% accuracy [14]. "
            "Baseline architectures evaluated in prior art include U-Net, YOLOv8-seg, and ResNet-50 under ISO 17636-2."
        ),
        (
            "# Chapter 2. Pipeline Architecture and Primary Dataset Collection\n\n"
            "We manually curated and annotated a unique primary dataset of N = 1800 digital X-ray radiographs "
            "of welded joints (COCO polygon format, 2048x2048 resolution, 16-bit grayscale). "
            "We trained an Attention U-Net using Focal Tversky Loss to handle micro-crack class imbalance."
        ),
        (
            "# Chapter 3. Experimental Evaluation and Error Analysis\n\n"
            "Initially we trained a baseline YOLOv8-seg model without preprocessing, but it failed to detect "
            "micro-cracks thinner than 2px due to aggressive strided downsampling (F1 = 0.31), so it was discarded.\n\n"
            "Table 3.4. Segmentation Accuracy and CPU Latency Across Defect Classes\n"
            "| Defect Class | Sample Size | F1-Score | CPU Latency |\n"
            "|---|---|---|---|\n"
            "| Gas Porosity | 850 | 0.94 | 3.2 sec/frame |\n"
            "| Slag Inclusions | 620 | 0.91 | 3.2 sec/frame |\n"
            "| Low-Contrast / Coherent Speckle Noise | 330 | 0.52 | 3.4 sec/frame |\n\n"
            "Implementation Note: Within the current prototype, the live video stream ingestion module is "
            "implemented as a synchronous local folder file-reading stub without batching. "
            "Under low-contrast coherent speckle noise, F1 drops to 0.52."
        ),
        (
            "# Conclusion and Future Work\n\n"
            "We have developed a production-ready real-time software complex for automated weld defect "
            "recognition achieving an average accuracy of 94%. All stated objectives have been fully met.\n\n"
            "## Future Work\n"
            "In future work, we plan to build a convenient web interface for inspectors and an iOS mobile app. "
            "Additionally, we must integrate a multiplicative speckle-noise suppression filter that preserves crack edges "
            "and quantize the model to ONNX Runtime INT8 to reduce inference latency below 30 ms per frame."
        ),
    ]

    for p_text in pages_content:
        page = doc.new_page(width=595, height=842)
        rect = fitz.Rect(45, 45, 550, 800)
        page.insert_textbox(rect, p_text, fontsize=11, fontname="helv")

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


# ==============================================================================
# 2. PERSISTENCE HELPER FUNCTION (POSTGRESQL + QDRANT)
# ==============================================================================
async def _insert_seeded_project(
    db: AsyncSession,
    passport: CoreProjectSchema,
    index_in_qdrant: bool = True,
) -> uuid.UUID:
    proj_uuid = uuid.UUID(passport.project_id) if len(passport.project_id) == 36 else deterministic_uuid5("PROJ", passport.project_id)
    rev_uuid = deterministic_uuid5("REV", str(proj_uuid), 1)
    passport.project_id = str(proj_uuid)
    passport.revision_id = str(rev_uuid)

    full_text_for_fp = (
        f"{passport.meta.title} {passport.supply_assets.data_summary} "
        f"{passport.supply_assets.code_summary} {passport.deep_harvest_audit.reality_vs_conclusion_gap.middle_chapter_reality}"
    )
    mh_sig = compute_minhash_signature(full_text_for_fp)
    anchors, anchors_hash = extract_universal_hard_anchors(
        full_text_for_fp,
        [passport.artifact_verification.repo_url] if passport.artifact_verification.repo_url else [],
    )

    dedup_key = hashlib.sha256(f"{passport.project_id}:{passport.meta.title}".encode("utf-8")).hexdigest()

    proj_row = Project(
        id=proj_uuid,
        lineage_dedup_key=dedup_key,
        current_revision_id=rev_uuid,
        title=passport.meta.title[:295],
        publication_year=passport.meta.year,
        department=passport.meta.department[:115],
        author_name=passport.meta.author[:145],
        supervisor_name=passport.meta.supervisor[:145],
        domain_profile=passport.meta.domain_profile.value,
        modality=passport.meta.modality.value,
        primary_language=passport.meta.primary_language[:30],
        lifecycle_archetype=passport.lifecycle_archetype.value,
        status=ProjectStatus.COMPLETED.value,
        final_handover_score=Decimal(str(passport.scoring.final_handover_score)),
        minhash_signature=mh_sig,
        hard_anchors_hash=anchors_hash,
        hard_anchors_json=anchors,
    )
    db.add(proj_row)

    for s_idx, s_it in enumerate(passport.supply_assets.atomic_supply_items):
        s_it.item_id = str(deterministic_uuid5("SUPPLY", rev_uuid, s_idx))
    for d_idx, d_it in enumerate(passport.demand_horizon.atomic_demand_items):
        d_it.item_id = str(deterministic_uuid5("DEMAND", rev_uuid, d_idx))

    rev_row = ProjectRevision(
        id=rev_uuid,
        project_id=proj_uuid,
        revision_number=1,
        pdf_sha256=dedup_key,
        pdf_blob_path="/var/lib/horizon/blobs/demo_pdfs/demo_weld_xray_thesis.pdf",
        markdown_zst_path="",
        passport_json=passport.model_dump(mode="json"),
        llm_audit_flags=passport.llm_audit_flags.model_dump(mode="json"),
        raw_code_score=passport.scoring.raw_code_score,
        raw_data_score=passport.scoring.raw_data_score,
        validity_score=passport.scoring.validity_score,
        horizon_component_score=passport.scoring.roadmap_or_maturity_score,
        time_decay_code=Decimal(str(passport.scoring.time_decay_code)),
        time_decay_data=Decimal(str(passport.scoring.time_decay_data)),
        gap_severity=passport.deep_harvest_audit.reality_vs_conclusion_gap.gap_severity.value,
        security_alert=passport.security_alert,
        plagiarism_alert=passport.plagiarism_alert,
    )
    db.add(rev_row)

    probe_dto = passport.artifact_verification
    db.add(
        ArtifactProbe(
            id=uuid.uuid4(),
            revision_id=rev_uuid,
            repo_url=probe_dto.repo_url,
            latest_commit_sha=probe_dto.latest_commit_sha or "a8f4c21",
            repo_alive=probe_dto.repo_alive,
            has_dependencies=probe_dto.has_dependencies,
            has_clean_paths=probe_dto.has_clean_paths,
            has_data_artifact=probe_dto.has_data_artifact,
            has_license=probe_dto.has_license,
            probe_status=probe_dto.probe_status.value,
            probe_diagnostics_json=probe_dto.diagnostics,
        )
    )

    eff_asset = Decimal(
        str(
            round(
                passport.scoring.raw_code_score * passport.scoring.time_decay_code
                + passport.scoring.raw_data_score * passport.scoring.time_decay_data,
                2,
            )
        )
    )

    for idx, s_it in enumerate(passport.supply_assets.atomic_supply_items):
        db.add(
            AtomicSupplyItem(
                id=deterministic_uuid5("SUPPLY", rev_uuid, idx),
                project_id=proj_uuid,
                revision_id=rev_uuid,
                item_index=idx,
                asset_type=s_it.asset_type,
                domain_specific_text=s_it.domain_specific_text,
                abstract_math_function=s_it.abstract_math_function,
                operating_envelope=s_it.operating_envelope.model_dump(mode="json"),
                effective_asset_score=eff_asset,
            )
        )

    for idx, d_it in enumerate(passport.demand_horizon.atomic_demand_items):
        db.add(
            AtomicDemandItem(
                id=deterministic_uuid5("DEMAND", rev_uuid, idx),
                project_id=proj_uuid,
                revision_id=rev_uuid,
                item_index=idx,
                macro_category=d_it.macro_category.value,
                source_section=d_it.source,
                claim_status=d_it.claim_status.value,
                task_description=d_it.task_description,
                abstract_math_function=d_it.abstract_math_function,
                operating_envelope=d_it.operating_envelope.model_dump(mode="json"),
            )
        )

    await db.flush()

    if index_in_qdrant:
        meat = ChapterMeatSchema(
            chapter_heading="Chapter 3. Experimental Verification",
            hard_specs=[
                HardSpecExtract(
                    parameter_or_table="Experimental sample and metrics",
                    exact_value_or_schema=passport.supply_assets.data_summary,
                    source_page=48,
                )
            ],
            discarded_approaches=passport.deep_harvest_audit.discarded_approaches,
        )
        centroid, _ = await index_project_vectors(
            project_id=proj_uuid,
            revision_id=rev_uuid,
            revision_number=1,
            passport=passport,
            middle_extracts=[meat],
        )
        proj_row.semantic_centroid_fp32 = centroid.tobytes()

    return proj_uuid


# ==============================================================================
# 3. SEEDING 7 FLAGSHIPS + 193 BACKGROUND UNIVERSITY CORPUS
# ==============================================================================
async def seed_university_corpus(db: AsyncSession) -> dict[str, Any]:
    """Seeds the 7 Flagship English Projects + 193 Analytical Projects across 5 University Profiles."""
    generate_sample_demo_pdf()

    # 1. FLAGSHIP #1: Weld X-Ray Segmentation (Canonical Spec Example §5.7.2)
    p1_weld = CoreProjectSchema(
        project_id="vkr_2025_cs_042",
        lifecycle_archetype=LifecycleArchetype.RELAY_CANDIDATE,
        lineage=LineageInfoSchema(
            generation=2,
            forked_from_project_id="vkr_2024_cs_019",
            inherited_asset_type="dataset",
            citation_contract_active=True,
        ),
        meta=ProjectMetaSchema(
            title="Automated Defect Segmentation in X-Ray Radiographs of Welded Joints",
            year=2025,
            department="Department of Computer Vision & NDT",
            author="Elias Vance",
            supervisor="Prof. Arthur Pendelton",
            domain_profile=DomainProfile.IT_AND_DATA_SCIENCE,
            modality=ModalityType.image,
            primary_language="Python",
            frameworks=["PyTorch", "OpenCV", "ONNX"],
        ),
        artifact_verification=ArtifactVerificationDTO(
            repo_url="https://github.com/example/weld-xray-seg",
            repo_alive=True,
            has_dependencies=True,
            has_clean_paths=True,
            has_data_artifact=True,
            has_license=True,
            probe_status=ProbeStatus.VERIFIED,
            detected_stack=["Python", "PyTorch"],
            diagnostics={"non_empty_files_count": 18, "data_artifacts": ["datasets/weld_coco_1800.parquet (14.2 MB)"]},
        ),
        deep_harvest_audit=DeepHarvestAuditSchema(
            reality_vs_conclusion_gap=RealityVsConclusionGapSchema(
                conclusion_claim="Developed a real-time weld defect recognition system achieving 94% accuracy.",
                middle_chapter_reality="Page 51 (Table 3.4): On low-contrast radiographs with coherent speckle noise, F1 drops to 0.52; CPU inference takes 3.2 sec/frame, and video stream ingestion is a local folder file-reading stub.",
                gap_severity=GapSeverity.HIGH,
                source_page=51,
            ),
            commission_defense_questions=[
                "In the Conclusion (p. 78) you claim real-time operation, yet Table 3.4 (p. 51) reports 3.2 sec/frame on CPU reading from a local folder stub. How will this handle live conveyor streams?",
                "How do you plan to resolve the F1-score drop to 0.52 on low-contrast radiographs without retraining the U-Net backbone?",
                "Was cross-validation performed on radiographs from different X-ray tubes to rule out sensor-specific overfitting?",
            ],
            prior_art_radar=PriorArtRadarSchema(
                similar_past_projects=[
                    PriorArtProjectRef(
                        project_id="vkr_2023_ndt_008",
                        title="Porosity and Slag Inclusion Detection in Pipeline Welds",
                        year=2023,
                        department="Department of Nondestructive Testing",
                        author="Victor Sterling",
                        similarity_score=0.86,
                        similarity_note="Overlaps on pore/crack defect taxonomy (F1=0.85); add baseline comparison to Chapter 1.",
                    )
                ]
            ),
            discarded_approaches=[
                DiscardedApproachExtract(
                    method="Baseline YOLOv8-seg without contrast preprocessing",
                    failure_reason="Fails to detect micro-cracks thinner than <2px due to strided downsampling (F1 = 0.31)",
                    source_location="Chapter 3.1, p. 38",
                    source_page=38,
                )
            ],
            future_work_linter_items=[
                FutureWorkLinterItem(
                    original_sentence="In the future we plan to develop a convenient web interface for inspectors and an iOS mobile application...",
                    verdict="FLUFF",
                    reason_badge="REJECTED: UI/Product Fluff — 0 pts",
                    points_impact=0,
                ),
                FutureWorkLinterItem(
                    original_sentence="...and also expand the sample of radiographs...",
                    verdict="WEAK_SPECIFICITY",
                    reason_badge="WEAK SPECIFICITY: No target sample parameters",
                    points_impact=0,
                ),
                FutureWorkLinterItem(
                    original_sentence="...integrate a speckle-noise suppression filter without blurring crack edges and quantize inference to ONNX Runtime INT8 (<30 ms/frame).",
                    verdict="ACTIONABLE_RD",
                    reason_badge="EXTRACTED TO DEMAND: Target metric (<30ms) + Stack (ONNX INT8) + Task — +30 pts",
                    points_impact=30,
                ),
            ],
        ),
        supply_assets=SupplyAssetsSectionSchema(
            code_summary="Attention U-Net training pipeline with custom Focal Tversky Loss",
            data_summary="Curated dataset of 1,800 annotated weld X-ray radiographs (COCO polygons)",
            atomic_supply_items=[
                AtomicSupplySchema(
                    asset_type="dataset",
                    domain_specific_text="Annotated dataset of 1,800 weld X-ray radiographs in COCO polygon format",
                    abstract_math_function="Annotated 2D grayscale high-contrast defect segmentation dataset with imbalanced micro-crack polygon masks (1800 samples)",
                    operating_envelope=OperatingEnvelopeSchema(
                        domain_env=DomainEnvType.industrial_shopfloor,
                        compatible_envs=[DomainEnvType.industrial_shopfloor, DomainEnvType.in_vivo_clinical, DomainEnvType.pure_software_cloud],
                        io_signature="2D_grayscale_matrix -> polygon_masks",
                        hard_preconditions=["grayscale_transmission_imaging"],
                    ),
                )
            ],
        ),
        demand_horizon=DemandHorizonSectionSchema(
            bottleneck_macro_category=BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS,
            bottleneck_cluster_label="Multiplicative coherent speckle noise & low contrast on 2D grayscale imagery",
            filtered_fluff_items=[
                "Build an iOS mobile application for field inspectors",
                "Add OAuth2 user authentication dashboard",
            ],
            atomic_demand_items=[
                AtomicDemandSchema(
                    source="Future_Work_Section (p. 76) + Middle_Stub (p. 51)",
                    macro_category=BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS,
                    claim_status=ClaimStatus.OPEN,
                    task_description="Integrate a pre-filtering module to suppress granular speckle noise without blurring micro-crack boundaries",
                    abstract_math_function="Suppression of multiplicative granular coherent noise (speckle) on 2D grayscale intensity matrices while preserving high-frequency edge gradients",
                    operating_envelope=OperatingEnvelopeSchema(
                        domain_env=DomainEnvType.industrial_shopfloor,
                        compatible_envs=[DomainEnvType.in_vivo_clinical, DomainEnvType.outdoor_terrestrial, DomainEnvType.pure_software_cloud],
                        io_signature="2D_grayscale_matrix -> 2D_grayscale_matrix_denoised",
                    ),
                    source_page=51,
                ),
                AtomicDemandSchema(
                    source="Middle_Stub (p. 51)",
                    macro_category=BottleneckMacroCategory.SYSTEM_INTEGRATION_AND_PROD,
                    claim_status=ClaimStatus.OPEN,
                    task_description="Quantize U-Net to ONNX Runtime / TensorRT INT8 to cut latency from 3.2s to <30ms per frame",
                    abstract_math_function="INT8 post-training quantization and graph fusion of convolutional and spectral networks for sub-30ms real-time edge inference",
                    operating_envelope=OperatingEnvelopeSchema(
                        domain_env=DomainEnvType.embedded_edge,
                        compatible_envs=[DomainEnvType.industrial_shopfloor, DomainEnvType.embedded_edge, DomainEnvType.pure_software_cloud],
                        io_signature="FP32_weights -> INT8_engine",
                    ),
                    source_page=51,
                ),
            ],
        ),
        llm_audit_flags=LLMAuditFlagsSchema(
            has_software_code=True,
            is_unique_primary_dataset=True,
            has_baseline_and_split=True,
            suspect_data_leakage=False,
            has_target_metric_in_roadmap=True,
            has_concrete_method_in_roadmap=True,
            is_fully_completed_gold_standard=False,
            has_structured_appendix=True,
            has_reproducible_methodology=True,
        ),
        scoring=ScoringBreakdownSchema(
            scoring_mode="SOFTWARE_CODE_AND_DATA",
            raw_code_score=25,
            raw_data_score=25,
            validity_score=20,
            roadmap_or_maturity_score=30,
            time_decay_code=0.64,
            time_decay_data=0.90,
            final_handover_score=88.5,
            status="High-Potential Relay Candidate",
            improvement_recipes=[
                "Replace synchronous local folder file-reading stub (p. 51) with an async ring-buffer video stream reader."
            ],
        ),
    )

    # 2. FLAGSHIP #2: Radiophysics Coherent Speckle Filter Donor (92% Synergy Match with Project A!)
    p2_radiophys_donor = CoreProjectSchema(
        project_id="vkr_2024_rf_011",
        lifecycle_archetype=LifecycleArchetype.GOLD_STANDARD_COMPLETED,
        meta=ProjectMetaSchema(
            title="Adaptive Anisotropic Wavelet Filtering of Multiplicative Clutter in Coherent SAR Radar",
            year=2024,
            department="Department of Radiophysics & Signal Processing",
            author="Alexei Sokolov",
            supervisor="Prof. Sergei Gromov",
            domain_profile=DomainProfile.ENGINEERING_AND_HARDWARE,
            modality=ModalityType.image,
            primary_language="Python",
            frameworks=["NumPy", "PyWavelets", "Numba", "OpenCV"],
        ),
        artifact_verification=ArtifactVerificationDTO(
            repo_url="https://github.com/example/coherent-speckle-wavelet-filter",
            repo_alive=True,
            has_dependencies=True,
            has_clean_paths=True,
            has_data_artifact=True,
            has_license=True,
            probe_status=ProbeStatus.VERIFIED,
            detected_stack=["Python", "C/C++"],
        ),
        deep_harvest_audit=DeepHarvestAuditSchema(
            reality_vs_conclusion_gap=RealityVsConclusionGapSchema(
                conclusion_claim="Developed a fast edge-preserving speckle suppression filter (+6.4 dB PSNR).",
                middle_chapter_reality="All stated metrics verified in Table 2.3 (p. 41) on 2048x2048 matrices (filtering latency 4.1 ms/frame).",
                gap_severity=GapSeverity.NONE,
                source_page=41,
            ),
            commission_defense_questions=[
                "Can this anisotropic wavelet kernel be directly transferred to medical ultrasound and X-ray imagery without recalibrating damping factors?",
                "What is the computational complexity when synthesized on FPGA?",
                "At what SNR threshold do sub-pixel linear structures begin to attenuate?",
            ],
        ),
        supply_assets=SupplyAssetsSectionSchema(
            code_summary="Production Python/Numba module for edge-preserving multiplicative speckle suppression (4.1 ms/frame)",
            data_summary="Mathematical proofs and gamma-distributed coherent noise calibration matrices",
            atomic_supply_items=[
                AtomicSupplySchema(
                    asset_type="code_module",
                    domain_specific_text="Edge-preserving multiplicative coherent speckle noise filtering library (Python/Numba, 4.1 ms/frame)",
                    abstract_math_function="Suppression of multiplicative granular coherent noise (speckle) on 2D grayscale intensity matrices while preserving high-frequency edge gradients",
                    operating_envelope=OperatingEnvelopeSchema(
                        domain_env=DomainEnvType.outdoor_terrestrial,
                        compatible_envs=[
                            DomainEnvType.industrial_shopfloor,
                            DomainEnvType.in_vivo_clinical,
                            DomainEnvType.pure_software_cloud,
                        ],
                        io_signature="2D_grayscale_matrix -> 2D_grayscale_matrix_denoised",
                    ),
                )
            ],
        ),
        demand_horizon=DemandHorizonSectionSchema(
            bottleneck_macro_category=BottleneckMacroCategory.DOMAIN_VALIDATION,
            bottleneck_cluster_label="Cross-domain validation on biomedical ultrasound and industrial radiography",
            atomic_demand_items=[],
        ),
        llm_audit_flags=LLMAuditFlagsSchema(
            has_software_code=True,
            is_unique_primary_dataset=True,
            has_baseline_and_split=True,
            suspect_data_leakage=False,
            is_fully_completed_gold_standard=True,
            has_structured_appendix=True,
            has_reproducible_methodology=True,
        ),
        scoring=ScoringBreakdownSchema(
            scoring_mode="SOFTWARE_CODE_AND_DATA",
            raw_code_score=25,
            raw_data_score=25,
            validity_score=20,
            roadmap_or_maturity_score=30,
            time_decay_code=0.82,
            time_decay_data=0.95,
            final_handover_score=94.2,
            status="Gold Standard / Pure Supply Donor (TRL 6-7)",
        ),
    )

    # 3. FLAGSHIP #3: MedTech Ultrasound Segmentation (Gen 2 in Lineage Graph + Synergy Consumer)
    p3_medtech_ultrasound = CoreProjectSchema(
        project_id="vkr_2025_med_019",
        lifecycle_archetype=LifecycleArchetype.RELAY_CANDIDATE,
        lineage=LineageInfoSchema(
            generation=2,
            forked_from_project_id="vkr_2024_med_004",
            inherited_asset_type="dataset",
            citation_contract_active=True,
        ),
        meta=ProjectMetaSchema(
            title="Automated Focal Liver Lesion Segmentation on Handheld Point-of-Care Ultrasound",
            year=2025,
            department="Department of Biomedical Engineering (MedTech)",
            author="Elena Smirnova",
            supervisor="Dr. Konstantin Belov, MD",
            domain_profile=DomainProfile.NATURAL_AND_BIOMEDICAL,
            modality=ModalityType.image,
            primary_language="Python",
            frameworks=["PyTorch", "MONAI", "SimpleITK"],
        ),
        artifact_verification=ArtifactVerificationDTO(
            repo_url="https://github.com/example/ultrasound-liver-monai",
            repo_alive=True,
            has_dependencies=True,
            has_clean_paths=True,
            has_data_artifact=True,
            has_license=True,
            probe_status=ProbeStatus.VERIFIED,
            detected_stack=["Python", "MONAI"],
        ),
        deep_harvest_audit=DeepHarvestAuditSchema(
            reality_vs_conclusion_gap=RealityVsConclusionGapSchema(
                conclusion_claim="Achieved 84% clinical Dice segmentation accuracy for handheld ultrasound scanners.",
                middle_chapter_reality="Page 44: On handheld piezo probes, granular acoustic speckle noise causes Dice to drop to 0.61, and the 420 MB model exceeds portable scanner memory.",
                gap_severity=GapSeverity.MEDIUM,
                source_page=44,
            ),
            commission_defense_questions=[
                "How will a 420 MB unquantized checkpoint run on a battery-powered handheld ultrasound edge processor?",
                "Why was isotropic Gaussian smoothing used when it blurs vascular lesion boundaries?",
                "What was the multi-center patient cohort size (N=?) validated by independent radiologists?",
            ],
            discarded_approaches=[
                DiscardedApproachExtract(
                    method="7x7 Median Filtering prior to U-Net encoder",
                    failure_reason="Erases hyperechoic lesion margins smaller than <4 mm (Dice drops to 0.49)",
                    source_location="Chapter 2.4, p. 33",
                    source_page=33,
                )
            ],
        ),
        supply_assets=SupplyAssetsSectionSchema(
            code_summary="MONAI Attention U-Net 2D/3D clinical training pipeline",
            data_summary="Radiologist-verified abdominal ultrasound corpus (3,000 scans across 240 patients)",
            atomic_supply_items=[
                AtomicSupplySchema(
                    asset_type="dataset",
                    domain_specific_text="Annotated clinical corpus of 3,000 abdominal ultrasound scans with pathology masks (DICOM + NIfTI)",
                    abstract_math_function="Annotated 2D medical ultrasound grayscale image corpus with expert segmentation masks (3000 samples)",
                    operating_envelope=OperatingEnvelopeSchema(
                        domain_env=DomainEnvType.in_vivo_clinical,
                        compatible_envs=[DomainEnvType.in_vivo_clinical, DomainEnvType.pure_software_cloud],
                        io_signature="2D_grayscale_matrix -> binary_segmentation_mask",
                    ),
                )
            ],
        ),
        demand_horizon=DemandHorizonSectionSchema(
            bottleneck_macro_category=BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS,
            bottleneck_cluster_label="Multiplicative coherent speckle noise & low contrast on 2D grayscale imagery",
            atomic_demand_items=[
                AtomicDemandSchema(
                    source="Middle_Chapter_Audit (p. 44)",
                    macro_category=BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS,
                    claim_status=ClaimStatus.OPEN,
                    task_description="Segmentation accuracy degradation due to multiplicative acoustic speckle noise on portable ultrasound probes",
                    abstract_math_function="Suppression of multiplicative granular coherent noise (speckle) on 2D grayscale intensity matrices while preserving high-frequency edge gradients",
                    operating_envelope=OperatingEnvelopeSchema(
                        domain_env=DomainEnvType.in_vivo_clinical,
                        compatible_envs=[DomainEnvType.outdoor_terrestrial, DomainEnvType.industrial_shopfloor, DomainEnvType.pure_software_cloud],
                        io_signature="2D_grayscale_matrix -> 2D_grayscale_matrix_denoised",
                    ),
                    source_page=44,
                )
            ],
        ),
        llm_audit_flags=LLMAuditFlagsSchema(
            has_software_code=True,
            is_unique_primary_dataset=True,
            has_baseline_and_split=True,
            suspect_data_leakage=False,
            has_target_metric_in_roadmap=True,
            has_concrete_method_in_roadmap=True,
            has_structured_appendix=True,
            has_reproducible_methodology=True,
        ),
        scoring=ScoringBreakdownSchema(
            scoring_mode="SOFTWARE_CODE_AND_DATA",
            raw_code_score=25,
            raw_data_score=25,
            validity_score=20,
            roadmap_or_maturity_score=28,
            time_decay_code=0.64,
            time_decay_data=0.90,
            final_handover_score=86.5,
            status="High-Potential Relay Candidate",
        ),
    )

    # 4. FLAGSHIP #4: Gen 1 (2024) — Root of the Ultrasound Lineage Tree
    p4_medtech_gen1 = CoreProjectSchema(
        project_id="vkr_2024_med_004",
        lifecycle_archetype=LifecycleArchetype.RELAY_CANDIDATE,
        lineage=LineageInfoSchema(generation=1),
        meta=ProjectMetaSchema(
            title="Primary Clinical Ultrasound Image Bank Acquisition & Baseline Otsu Thresholding",
            year=2024,
            department="Department of Biomedical Engineering (MedTech)",
            author="Dmitry Kozlov",
            supervisor="Dr. Konstantin Belov, MD",
            domain_profile=DomainProfile.NATURAL_AND_BIOMEDICAL,
            modality=ModalityType.image,
            primary_language="Python",
            frameworks=["OpenCV", "Scikit-Image"],
        ),
        artifact_verification=ArtifactVerificationDTO(
            repo_url="https://zenodo.org/record/1094821",
            repo_alive=True,
            has_dependencies=True,
            has_clean_paths=True,
            has_data_artifact=True,
            has_license=True,
            probe_status=ProbeStatus.VERIFIED,
            detected_stack=["Python"],
        ),
        deep_harvest_audit=DeepHarvestAuditSchema(
            reality_vs_conclusion_gap=RealityVsConclusionGapSchema(
                conclusion_claim="Collected primary dataset of 3,000 ultrasound scans; baseline Otsu segmentation reached 68%.",
                middle_chapter_reality="Page 39: Global thresholding fails under acoustic shadowing; deep encoder-decoder models required.",
                gap_severity=GapSeverity.LOW,
                source_page=39,
            ),
            commission_defense_questions=[
                "Is 68% accuracy sufficient for clinical triage?",
                "How was inter-observer agreement measured between the two annotating radiologists?",
                "How did you normalize acoustic gain across different ultrasound machines?",
            ],
        ),
        supply_assets=SupplyAssetsSectionSchema(
            code_summary="DICOM de-identification and histogram equalization scripts",
            data_summary="Primary clinical ultrasound corpus (3,000 scans, Gen 1)",
            atomic_supply_items=[
                AtomicSupplySchema(
                    asset_type="dataset",
                    domain_specific_text="Primary clinical archive of 3,000 abdominal ultrasound scans",
                    abstract_math_function="Raw 2D clinical ultrasound acoustic backscatter image archive",
                )
            ],
        ),
        demand_horizon=DemandHorizonSectionSchema(
            bottleneck_macro_category=BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS,
            bottleneck_cluster_label="Multiplicative coherent speckle noise & low contrast on 2D grayscale imagery",
            atomic_demand_items=[
                AtomicDemandSchema(
                    task_description="Transition from Otsu thresholding to deep attention U-Net segmentation",
                    abstract_math_function="Deep convolutional encoder-decoder segmentation on noisy 2D matrices",
                    claim_status=ClaimStatus.COMPLETED,
                )
            ],
        ),
        llm_audit_flags=LLMAuditFlagsSchema(
            has_software_code=True,
            is_unique_primary_dataset=True,
            has_baseline_and_split=True,
            has_structured_appendix=True,
            has_reproducible_methodology=True,
        ),
        scoring=ScoringBreakdownSchema(
            raw_code_score=20,
            raw_data_score=25,
            validity_score=20,
            roadmap_or_maturity_score=25,
            time_decay_code=0.41,
            time_decay_data=0.82,
            final_handover_score=78.7,
            status="Completed Gen-1 Foundation",
        ),
    )

    # 5. FLAGSHIP #5: School of Law (HIPAA / GDPR k-Anonymity Kit closing MedTech/AI Legal Bottlenecks!)
    p5_law_donor = CoreProjectSchema(
        project_id="vkr_2025_law_003",
        lifecycle_archetype=LifecycleArchetype.GOLD_STANDARD_COMPLETED,
        meta=ProjectMetaSchema(
            title="Regulatory Framework & Algorithmic k-Anonymity Protocol for Clinical & Enterprise Data Sharing (HIPAA / GDPR)",
            year=2025,
            department="School of Law & AI Governance",
            author="Anna Volkova",
            supervisor="Prof. Tatiana Zakharova, JD",
            domain_profile=DomainProfile.HUMANITIES_SOCIAL_AND_LAW,
            modality=ModalityType.legal_normative,
            primary_language="Legal Framework / SQL",
            frameworks=["GDPR Art. 89", "HIPAA Safe Harbor", "DICOM De-identification"],
        ),
        artifact_verification=ArtifactVerificationDTO(
            repo_url=None,
            has_data_artifact=True,
            probe_status=ProbeStatus.NO_REPO_METHODOLOGY_ONLY,
            diagnostics={"mode": "In-Document Empirical / Methodology Audit", "has_structured_appendix_in_pdf": True},
        ),
        deep_harvest_audit=DeepHarvestAuditSchema(
            reality_vs_conclusion_gap=RealityVsConclusionGapSchema(
                conclusion_claim="Developed a complete legal agreement package and k-anonymity attribute masking matrix for hospital-to-university dataset transfers.",
                middle_chapter_reality="Appendices A–D (pp. 62–79) contain ready-to-sign IRB protocols, DICOM tag stripping tables, and Data Use Agreements.",
                gap_severity=GapSeverity.NONE,
                source_page=62,
            ),
            commission_defense_questions=[
                "Does k >= 5 anonymity satisfy GDPR Recital 26 against linkage attacks on rare ICD-10 diagnoses?",
                "How are IP rights partitioned when a neural network is trained on de-identified hospital records?",
                "What audit trail is required by the university IRB before external release?",
            ],
        ),
        supply_assets=SupplyAssetsSectionSchema(
            code_summary="Formalized k-anonymity / l-diversity compliance protocol and IRB Data Use Agreement templates",
            data_summary="Registry of 140 regulatory compliance cases + ready-to-deploy DICOM/tabular de-identification matrices in Appendix",
            atomic_supply_items=[
                AtomicSupplySchema(
                    asset_type="legal_framework",
                    domain_specific_text="Approved HIPAA/GDPR legal compliance kit and k-anonymity de-identification matrix for clinical & enterprise datasets",
                    abstract_math_function="K-anonymity and differential privacy regulatory compliance transformation protocol for sensitive tabular and imaging records",
                    operating_envelope=OperatingEnvelopeSchema(
                        domain_env=DomainEnvType.regulatory_legal_framework,
                        compatible_envs=[
                            DomainEnvType.in_vivo_clinical,
                            DomainEnvType.socio_economic_organization,
                            DomainEnvType.pure_software_cloud,
                        ],
                        io_signature="raw_sensitive_records -> legally_compliant_anonymized_corpus",
                    ),
                )
            ],
        ),
        demand_horizon=DemandHorizonSectionSchema(
            bottleneck_macro_category=BottleneckMacroCategory.SYSTEM_INTEGRATION_AND_PROD,
            bottleneck_cluster_label="Automated k-anonymity verification CLI in hospital ingestion pipelines",
            atomic_demand_items=[],
        ),
        llm_audit_flags=LLMAuditFlagsSchema(
            has_software_code=False,
            is_unique_primary_dataset=True,
            has_baseline_and_split=True,
            suspect_data_leakage=False,
            is_fully_completed_gold_standard=True,
            has_structured_appendix=True,
            has_reproducible_methodology=True,
        ),
        scoring=ScoringBreakdownSchema(
            scoring_mode="EMPIRICAL_AND_METHODOLOGY",
            raw_code_score=25,
            raw_data_score=25,
            validity_score=20,
            roadmap_or_maturity_score=30,
            time_decay_code=0.86,
            time_decay_data=0.90,
            final_handover_score=94.0,
            status="Gold Standard / Pure Supply Donor (TRL 6-7)",
        ),
    )

    # 6. FLAGSHIP #6: Economics & Financial Engineering (420 Enterprise Panel Dataset)
    p6_econ_project = CoreProjectSchema(
        project_id="vkr_2025_econ_015",
        lifecycle_archetype=LifecycleArchetype.RELAY_CANDIDATE,
        meta=ProjectMetaSchema(
            title="Econometric Panel Modeling of Supply-Chain Cash-Flow Liquidity Shocks Across 420 Manufacturing Firms",
            year=2025,
            department="Department of Econometrics & Financial Engineering",
            author="Kirill Morozov",
            supervisor="Prof. Olga Lebedeva, PhD",
            domain_profile=DomainProfile.ECONOMICS_AND_MANAGEMENT,
            modality=ModalityType.tabular,
            primary_language="R / SQL",
            frameworks=["R", "plm", "Panel Econometrics"],
        ),
        artifact_verification=ArtifactVerificationDTO(
            repo_url="https://osf.io/9x4k2",
            repo_alive=True,
            has_dependencies=True,
            has_clean_paths=True,
            has_data_artifact=True,
            has_license=True,
            probe_status=ProbeStatus.VERIFIED,
            detected_stack=["R", "SQL"],
        ),
        deep_harvest_audit=DeepHarvestAuditSchema(
            reality_vs_conclusion_gap=RealityVsConclusionGapSchema(
                conclusion_claim="Built a universal 2-quarter liquidity shock forecasting model achieving ROC-AUC = 0.89.",
                middle_chapter_reality="Page 53 (Table 2.8): For heavy machinery firms with production cycles >180 days, ROC-AUC drops to 0.61 due to unmodeled accounts-receivable seasonality.",
                gap_severity=GapSeverity.MEDIUM,
                source_page=53,
            ),
            commission_defense_questions=[
                "How does the fixed-effects specification handle abrupt central bank interest rate regime shifts?",
                "What explains the ROC-AUC drop to 0.61 on long-cycle manufacturing firms in Table 2.8 (p. 53)?",
                "Did the Hausman test confirm fixed effects over random effects across all sub-sectors?",
            ],
            discarded_approaches=[
                DiscardedApproachExtract(
                    method="Classical 5-factor Altman Z-Score without sector calibration",
                    failure_reason="Produces 48% false-positive distress alerts on capital-intensive manufacturing firms",
                    source_location="Chapter 2.2, p. 36",
                    source_page=36,
                )
            ],
        ),
        supply_assets=SupplyAssetsSectionSchema(
            code_summary="R panel regression scripts and financial ratio calculators (EBITDA, NPV, DSCR)",
            data_summary="Cleaned 6-year balanced panel dataset of N = 420 manufacturing enterprises (10,080 firm-quarters)",
            atomic_supply_items=[
                AtomicSupplySchema(
                    asset_type="empirical_corpus",
                    domain_specific_text="Balanced 6-year financial panel dataset of 420 manufacturing firms (10,080 quarterly observations)",
                    abstract_math_function="Multivariate longitudinal panel time-series dataset with liquidity and solvency ratios (N=420 entities, 24 quarters)",
                    operating_envelope=OperatingEnvelopeSchema(
                        domain_env=DomainEnvType.socio_economic_organization,
                        compatible_envs=[DomainEnvType.socio_economic_organization, DomainEnvType.pure_software_cloud],
                        io_signature="multivariate_time_series_panel -> default_probability_vector",
                    ),
                )
            ],
        ),
        demand_horizon=DemandHorizonSectionSchema(
            bottleneck_macro_category=BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS,
            bottleneck_cluster_label="Non-linear seasonal time-series modeling on longitudinal panel data",
            atomic_demand_items=[
                AtomicDemandSchema(
                    source="Middle_Chapter_Audit (p. 53)",
                    macro_category=BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS,
                    claim_status=ClaimStatus.OPEN,
                    task_description="Integrate Temporal Fusion Transformer / CatBoost survival analysis to capture non-linear receivables seasonality",
                    abstract_math_function="Non-linear temporal fusion and gradient boosted survival analysis on imbalanced multivariate panel time-series",
                    operating_envelope=OperatingEnvelopeSchema(
                        domain_env=DomainEnvType.socio_economic_organization,
                        compatible_envs=[DomainEnvType.pure_software_cloud, DomainEnvType.socio_economic_organization],
                        io_signature="multivariate_time_series_panel -> calibrated_hazard_rate",
                    ),
                    source_page=53,
                )
            ],
        ),
        llm_audit_flags=LLMAuditFlagsSchema(
            has_software_code=False,
            is_unique_primary_dataset=True,
            has_baseline_and_split=True,
            suspect_data_leakage=False,
            has_target_metric_in_roadmap=True,
            has_concrete_method_in_roadmap=True,
            has_structured_appendix=True,
            has_reproducible_methodology=True,
        ),
        scoring=ScoringBreakdownSchema(
            scoring_mode="EMPIRICAL_AND_METHODOLOGY",
            raw_code_score=25,
            raw_data_score=25,
            validity_score=20,
            roadmap_or_maturity_score=28,
            time_decay_code=0.86,
            time_decay_data=0.90,
            final_handover_score=92.0,
            status="High-Potential Relay Candidate",
        ),
    )

    # 7. FLAGSHIP #7: Gold Standard TRL-7 Industrial Edge Product (Matches INT8 Quantization Demand!)
    p7_gold_trl = CoreProjectSchema(
        project_id="vkr_2025_eng_001",
        lifecycle_archetype=LifecycleArchetype.GOLD_STANDARD_COMPLETED,
        meta=ProjectMetaSchema(
            title="Real-Time Vibro-Acoustic Bearing Fault Diagnostics & INT8 Edge Inference Engine on STM32H7",
            year=2025,
            department="Department of Industrial Automation & Embedded Systems",
            author="Vladislav Kuznetsov",
            supervisor="Prof. Dmitry Orlov",
            domain_profile=DomainProfile.ENGINEERING_AND_HARDWARE,
            modality=ModalityType.signal,
            primary_language="C/C++",
            frameworks=["STM32CubeIDE", "CMSIS-DSP", "MODBUS RTU", "ONNX Runtime INT8"],
        ),
        artifact_verification=ArtifactVerificationDTO(
            repo_url="https://github.com/example/stm32h7-vibro-diagnostics",
            repo_alive=True,
            has_dependencies=True,
            has_clean_paths=True,
            has_data_artifact=True,
            has_license=True,
            probe_status=ProbeStatus.VERIFIED,
            detected_stack=["C/C++", "ONNX INT8"],
        ),
        deep_harvest_audit=DeepHarvestAuditSchema(
            reality_vs_conclusion_gap=RealityVsConclusionGapSchema(
                conclusion_claim="System completed 720-hour continuous shopfloor validation with 97.4% early fault detection accuracy and 7.8 ms latency.",
                middle_chapter_reality="All bench and shopfloor protocols verified in Chapter 4 (pp. 58–71); zero discrepancy with Conclusion.",
                gap_severity=GapSeverity.NONE,
                source_page=58,
            ),
            commission_defense_questions=[
                "Is the bill of materials (BOM) and firmware package ready for commercial licensing to industrial partners?",
                "What is the operating temperature ceiling of the piezo accelerometer frontend?",
                "What is the worst-case MODBUS RTU alarm frame jitter?",
            ],
        ),
        supply_assets=SupplyAssetsSectionSchema(
            code_summary="Automated ONNX-to-INT8 quantization & graph-fusion toolkit + STM32H7 CMSIS-DSP firmware (<8 ms inference)",
            data_summary="1,200-hour 48 kHz industrial bearing vibration spectrum archive",
            atomic_supply_items=[
                AtomicSupplySchema(
                    asset_type="code_module",
                    domain_specific_text="Automated ONNX Runtime / TensorRT INT8 post-training quantization and graph-fusion engine (<8 ms real-time inference)",
                    abstract_math_function="INT8 post-training quantization and graph fusion of convolutional and spectral networks for sub-30ms real-time edge inference",
                    operating_envelope=OperatingEnvelopeSchema(
                        domain_env=DomainEnvType.embedded_edge,
                        compatible_envs=[DomainEnvType.industrial_shopfloor, DomainEnvType.embedded_edge, DomainEnvType.pure_software_cloud],
                        io_signature="FP32_weights -> INT8_engine",
                    ),
                )
            ],
        ),
        demand_horizon=DemandHorizonSectionSchema(
            bottleneck_macro_category=BottleneckMacroCategory.SYSTEM_INTEGRATION_AND_PROD,
            bottleneck_cluster_label="Industrial patent filing & technology transfer showcase (TRL 7)",
            atomic_demand_items=[],
        ),
        llm_audit_flags=LLMAuditFlagsSchema(
            has_software_code=True,
            is_unique_primary_dataset=True,
            has_baseline_and_split=True,
            suspect_data_leakage=False,
            is_fully_completed_gold_standard=True,
            has_structured_appendix=True,
            has_reproducible_methodology=True,
        ),
        scoring=ScoringBreakdownSchema(
            scoring_mode="SOFTWARE_CODE_AND_DATA",
            raw_code_score=25,
            raw_data_score=25,
            validity_score=20,
            roadmap_or_maturity_score=30,
            time_decay_code=0.88,
            time_decay_data=0.95,
            final_handover_score=96.5,
            status="Gold Standard / Pure Supply Donor (TRL 6-7)",
        ),
    )

    flagships = [
        p1_weld,
        p2_radiophys_donor,
        p3_medtech_ultrasound,
        p4_medtech_gen1,
        p5_law_donor,
        p6_econ_project,
        p7_gold_trl,
    ]

    flagship_uuids: dict[str, uuid.UUID] = {}
    for fp in flagships:
        orig_key = fp.project_id
        u_id = await _insert_seeded_project(db, fp, index_in_qdrant=True)
        flagship_uuids[orig_key] = u_id

    db.add(
        ProjectLineageEdge(
            parent_project_id=flagship_uuids["vkr_2024_med_004"],
            child_project_id=flagship_uuids["vkr_2025_med_019"],
            inherited_asset_type="dataset",
            citation_contract_signed=True,
        )
    )

    # 8. BACKGROUND ANALYTICAL CORPUS (97+ Projects forming dense HDBSCAN Bottleneck Clusters)
    systemic_bottleneck_archetypes = [
        (
            19,
            BottleneckMacroCategory.DATA_SCARCITY_AND_ANNOTATION,
            DomainProfile.NATURAL_AND_BIOMEDICAL,
            ModalityType.image,
            DomainEnvType.in_vivo_clinical,
            "Python",
            ["Department of Biomedical Engineering (MedTech)", "Department of Radiology & Imaging", "Department of Computer Vision & NDT"],
            "Lack of radiologist-annotated 3D Chest CT scans for rare thoracic pathology segmentation",
            "Scarcity of expert-annotated 3D volumetric computed tomography matrices for rare pathology segmentation",
            "Preprocessed clinical DICOM cohort and baseline 3D normalization pipeline",
            "Preprocessed 3D volumetric medical imaging dataset with baseline normalization",
        ),
        (
            14,
            BottleneckMacroCategory.SYSTEM_INTEGRATION_AND_PROD,
            DomainProfile.ENGINEERING_AND_HARDWARE,
            ModalityType.signal,
            DomainEnvType.industrial_shopfloor,
            "C/C++",
            ["Department of Industrial Automation & Embedded Systems", "Department of Nondestructive Testing"],
            "Lack of access to industrial SCADA telemetry logs and OPC UA / MODBUS hardware-in-the-loop PLC testbed",
            "Lack of real-time industrial telemetry stream interface and PLC hardware-in-the-loop testbed",
            "State-space PID control loop mathematical model and synthetic sensor generator",
            "State-space control loop model and synthetic sensor telemetry generator",
        ),
        (
            16,
            BottleneckMacroCategory.COMPUTE_AND_HARDWARE,
            DomainProfile.IT_AND_DATA_SCIENCE,
            ModalityType.text,
            DomainEnvType.pure_software_cloud,
            "Python",
            ["Department of Computer Vision & NDT", "Department of Intelligent Information Systems"],
            "GPU VRAM deficit (>24 GB required) for fine-tuning and INT4/INT8 quantization of domain transformers",
            "Hardware VRAM bottleneck for fine-tuning and low-bit quantization of large sequence transformers",
            "Curated domain instruction-tuning dataset and evaluation benchmark",
            "Curated domain-specific instruction-tuning corpus and evaluation benchmark",
        ),
        (
            12,
            BottleneckMacroCategory.LEGAL_PRIVACY_AND_ACCESS,
            DomainProfile.ECONOMICS_AND_MANAGEMENT,
            ModalityType.tabular,
            DomainEnvType.socio_economic_organization,
            "R / SQL",
            ["Department of Econometrics & Financial Engineering", "Department of Biomedical Engineering (MedTech)"],
            "HIPAA / GDPR regulatory blocker preventing cross-departmental access to raw patient and transaction records",
            "K-anonymity and differential privacy regulatory compliance transformation protocol for sensitive tabular and imaging records",
            "Aggregated macroeconomic and enterprise panel specification",
            "Aggregated macroeconomic and organizational panel specification",
        ),
        (
            15,
            BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS,
            DomainProfile.ENGINEERING_AND_HARDWARE,
            ModalityType.image,
            DomainEnvType.industrial_shopfloor,
            "Python",
            ["Department of Computer Vision & NDT", "Department of Nondestructive Testing", "Department of Biomedical Engineering (MedTech)"],
            "Severe segmentation accuracy drop under multiplicative granular coherent speckle noise and surface glare",
            "Suppression of multiplicative granular coherent noise (speckle) on 2D grayscale intensity matrices while preserving high-frequency edge gradients",
            "Calibrated 2D grayscale defect imagery and baseline Canny/Sobel edge detector",
            "Calibrated 2D grayscale defect imagery and baseline edge detector",
        ),
        (
            11,
            BottleneckMacroCategory.DOMAIN_VALIDATION,
            DomainProfile.HUMANITIES_SOCIAL_AND_LAW,
            ModalityType.empirical_survey,
            DomainEnvType.regulatory_legal_framework,
            "R / SPSS",
            ["School of Law & AI Governance", "Department of Applied Sociology & Computational Linguistics"],
            "Shortage of domain practitioners (clinicians, legal scholars, linguists) for inter-annotator validation",
            "Inter-annotator agreement calibration and expert validation on multi-class empirical survey corpus",
            "Field sociological & linguistic survey response matrix (N = 1,200 respondents)",
            "Structured empirical survey response matrix and discourse corpus (N=1200)",
        ),
        (
            10,
            BottleneckMacroCategory.SCOPE_OVERRUN_AND_UNFINISHED,
            DomainProfile.IT_AND_DATA_SCIENCE,
            ModalityType.tabular,
            DomainEnvType.pure_software_cloud,
            "Python",
            ["Department of Intelligent Information Systems", "Department of Computer Vision & NDT"],
            "Author scope overrun: async streaming ingestion left as a synchronous local-folder file mock stub",
            "Replacement of synchronous local file mock stub with asynchronous streaming ingestion pipeline",
            "Trained gradient boosting classifier core and cleaned feature matrix",
            "Trained gradient boosting classifier core and cleaned feature matrix",
        ),
    ]

    authors_pool = [
        "Liam Carter", "Sophia Chen", "Noah Patel", "Olivia Kim", "Ethan Brooks", "Mia Morales",
        "Lucas Nguyen", "Amelia Novak", "Mason Lindqvist", "Harper Silva", "Logan O'Connor", "Evelyn Sato",
        "Alexander Ross", "Abigail Fischer", "Sebastian Moreno", "Emily Kowalski", "Jack Berger", "Aria Costa",
    ]
    supervisors_pool = [
        "Prof. Arthur Pendelton", "Dr. Konstantin Belov, MD", "Prof. Sergei Gromov",
        "Prof. Olga Lebedeva, PhD", "Prof. Tatiana Zakharova, JD", "Prof. Dmitry Orlov",
        "Dr. Marcus Vance", "Prof. Helena Sterling",
    ]

    proj_counter = 100
    for (
        count_in_group,
        macro_cat,
        prof,
        mod_type,
        d_env,
        lang,
        depts,
        demand_desc,
        demand_math,
        supply_desc,
        supply_math,
    ) in systemic_bottleneck_archetypes:
        for i in range(count_in_group):
            proj_counter += 1
            yr = 2023 + (proj_counter % 3)
            dept = depts[i % len(depts)]
            author = authors_pool[proj_counter % len(authors_pool)]
            sup = supervisors_pool[proj_counter % len(supervisors_pool)]

            is_gold_donor = (i == 0 and count_in_group >= 12)
            arch = (
                LifecycleArchetype.GOLD_STANDARD_COMPLETED
                if is_gold_donor
                else LifecycleArchetype.RELAY_CANDIDATE
            )

            raw_c = 25 if (i % 3 != 0) else 15
            raw_d = 25 if (i % 4 != 0) else 15
            val_s = 20 if (i % 5 != 0) else 10
            hor_s = 30 if is_gold_donor else (20 + (i % 10))
            dt = max(0.0, float(2026 - yr))
            dec_c = round(math.exp(-0.30 * dt), 3)
            dec_d = round(math.exp(-0.10 * dt), 3)
            final_sc = round(min(100.0, raw_c * dec_c + raw_d * dec_d + val_s + hor_s), 2)

            p_schema = CoreProjectSchema(
                project_id=f"vkr_{yr}_seed_{proj_counter}",
                lifecycle_archetype=arch,
                meta=ProjectMetaSchema(
                    title=f"{supply_desc[:75]} (Thesis Series #{proj_counter})",
                    year=yr,
                    department=dept,
                    author=author,
                    supervisor=sup,
                    domain_profile=prof,
                    modality=mod_type,
                    primary_language=lang,
                    frameworks=[lang, "Open Science Standard"],
                ),
                artifact_verification=ArtifactVerificationDTO(
                    repo_url=f"https://github.com/univ-archive/thesis-{yr}-{proj_counter}" if prof == DomainProfile.IT_AND_DATA_SCIENCE else None,
                    repo_alive=(prof == DomainProfile.IT_AND_DATA_SCIENCE),
                    has_dependencies=True,
                    has_clean_paths=True,
                    has_data_artifact=True,
                    has_license=True,
                    probe_status=ProbeStatus.VERIFIED if prof == DomainProfile.IT_AND_DATA_SCIENCE else ProbeStatus.NO_REPO_METHODOLOGY_ONLY,
                    detected_stack=[lang],
                ),
                deep_harvest_audit=DeepHarvestAuditSchema(
                    reality_vs_conclusion_gap=RealityVsConclusionGapSchema(
                        conclusion_claim="Target accuracy and performance benchmarks met on the laboratory testbed.",
                        middle_chapter_reality=f"Page {40 + (i % 20)}: Middle-chapter table reveals systemic bottleneck — {demand_desc}.",
                        gap_severity=GapSeverity.NONE if is_gold_donor else GapSeverity.MEDIUM,
                        source_page=40 + (i % 20),
                    ),
                    commission_defense_questions=[
                        f"How does the bottleneck \"{demand_desc[:90]}\" affect production deployment?",
                        "Were results benchmarked against prior theses from adjacent departments?",
                        "Is the primary sample size sufficient for statistical significance (p < 0.05)?",
                    ],
                ),
                supply_assets=SupplyAssetsSectionSchema(
                    code_summary=f"Validated prototype & analytical pipeline ({lang})",
                    data_summary=f"{supply_desc} (Project #{proj_counter})",
                    atomic_supply_items=[
                        AtomicSupplySchema(
                            asset_type="dataset",
                            domain_specific_text=f"{supply_desc} ({yr} Cohort, {dept})",
                            abstract_math_function=supply_math,
                            operating_envelope=OperatingEnvelopeSchema(
                                domain_env=d_env,
                                compatible_envs=[d_env, DomainEnvType.pure_software_cloud],
                                io_signature=f"{mod_type.value}_in -> {mod_type.value}_out",
                            ),
                        )
                    ],
                ),
                demand_horizon=DemandHorizonSectionSchema(
                    bottleneck_macro_category=macro_cat,
                    bottleneck_cluster_label=demand_desc[:100],
                    atomic_demand_items=[
                        AtomicDemandSchema(
                            source=f"Chapter 3, p. {40 + (i % 20)}",
                            macro_category=macro_cat,
                            claim_status=ClaimStatus.OPEN,
                            task_description=demand_desc,
                            abstract_math_function=demand_math,
                            operating_envelope=OperatingEnvelopeSchema(
                                domain_env=d_env,
                                compatible_envs=[d_env, DomainEnvType.pure_software_cloud],
                                io_signature=f"{mod_type.value}_raw -> {mod_type.value}_validated",
                            ),
                            source_page=40 + (i % 20),
                        )
                    ],
                ),
                llm_audit_flags=LLMAuditFlagsSchema(
                    has_software_code=(prof == DomainProfile.IT_AND_DATA_SCIENCE),
                    is_unique_primary_dataset=True,
                    has_baseline_and_split=True,
                    suspect_data_leakage=False,
                    has_target_metric_in_roadmap=True,
                    has_concrete_method_in_roadmap=True,
                    is_fully_completed_gold_standard=is_gold_donor,
                    has_structured_appendix=True,
                    has_reproducible_methodology=True,
                ),
                scoring=ScoringBreakdownSchema(
                    scoring_mode="SOFTWARE_CODE_AND_DATA" if prof == DomainProfile.IT_AND_DATA_SCIENCE else "EMPIRICAL_AND_METHODOLOGY",
                    raw_code_score=raw_c,
                    raw_data_score=raw_d,
                    validity_score=val_s,
                    roadmap_or_maturity_score=hor_s,
                    time_decay_code=dec_c,
                    time_decay_data=dec_d,
                    final_handover_score=final_sc,
                    status="Gold Standard / Pure Supply Donor (TRL 6-7)" if is_gold_donor else "High-Potential Relay Candidate",
                ),
            )
            await _insert_seeded_project(db, p_schema, index_in_qdrant=(i < 4))

    await db.commit()
    cluster_stats = await run_offline_hdbscan_reclustering(db)
    return {"seeded_projects": proj_counter - 100 + len(flagships), "clusters": cluster_stats}


async def _main() -> None:
    await init_postgres_schema()
    await init_qdrant_collections()
    async with db_session_context() as db:
        stats = await seed_university_corpus(db)
        print("Seeding finished:", stats)


if __name__ == "__main__":
    asyncio.run(_main())
