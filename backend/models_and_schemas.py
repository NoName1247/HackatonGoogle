"""
[2] Unified SQLAlchemy 2.0 ORM Models (PostgreSQL 16) and Pydantic v2 Schemas.
Supports all 5 university macro-profiles (IT & Data Science, Engineering & Hardware,
Natural & Biomedical Sciences, Economics & Management, Humanities, Social Sciences & Law),
3-factor anti-rewrite fingerprinting (MinHash + Universal Hard Anchors + Semantic Centroid),
and the canonical CoreProjectSchema.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ==============================================================================
# 1. DOMAIN ENUMERATIONS
# ==============================================================================
class DomainProfile(str, Enum):
    """5 universal macro-profiles across a research university."""
    IT_AND_DATA_SCIENCE = "IT_AND_DATA_SCIENCE"
    ENGINEERING_AND_HARDWARE = "ENGINEERING_AND_HARDWARE"
    NATURAL_AND_BIOMEDICAL = "NATURAL_AND_BIOMEDICAL"
    ECONOMICS_AND_MANAGEMENT = "ECONOMICS_AND_MANAGEMENT"
    HUMANITIES_SOCIAL_AND_LAW = "HUMANITIES_SOCIAL_AND_LAW"


class LifecycleArchetype(str, Enum):
    RELAY_CANDIDATE = "RELAY_CANDIDATE"
    GOLD_STANDARD_COMPLETED = "GOLD_STANDARD_COMPLETED"
    DEAD_END_ARCHIVE = "DEAD_END_ARCHIVE"


class ProjectStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"
    QUARANTINE = "QUARANTINE"


class ProbeStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    DEFERRED_RETRY = "DEFERRED_RETRY"
    PENDING_DOMAIN = "PENDING_DOMAIN"
    NO_REPO_METHODOLOGY_ONLY = "NO_REPO_METHODOLOGY_ONLY"


class GapSeverity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ZoneType(str, Enum):
    LIT_REVIEW = "LIT_REVIEW"
    CORE_ENG = "CORE_ENG"
    CLAIMS = "CLAIMS"


class ModalityType(str, Enum):
    image = "image"
    audio = "audio"
    text = "text"
    tabular = "tabular"
    signal = "signal"
    hardware = "hardware"
    empirical_survey = "empirical_survey"
    legal_normative = "legal_normative"
    multimodal = "multimodal"


class DomainEnvType(str, Enum):
    indoor_gps_denied = "indoor_gps_denied"
    outdoor_terrestrial = "outdoor_terrestrial"
    aerospace_celestial = "aerospace_celestial"
    in_vivo_clinical = "in_vivo_clinical"
    industrial_shopfloor = "industrial_shopfloor"
    embedded_edge = "embedded_edge"
    pure_software_cloud = "pure_software_cloud"
    socio_economic_organization = "socio_economic_organization"
    regulatory_legal_framework = "regulatory_legal_framework"
    wet_lab_experimental = "wet_lab_experimental"


class BottleneckMacroCategory(str, Enum):
    COMPUTE_AND_HARDWARE = "Compute & Hardware"
    DATA_SCARCITY_AND_ANNOTATION = "Data Scarcity & Annotation"
    ALGORITHMIC_LIMITATIONS = "Algorithmic Limitations"
    SYSTEM_INTEGRATION_AND_PROD = "System Integration & Prod"
    LEGAL_PRIVACY_AND_ACCESS = "Legal, Privacy & Access"
    DOMAIN_VALIDATION = "Domain Validation"
    SCOPE_OVERRUN_AND_UNFINISHED = "Scope Overrun & Unfinished Dev"


class ClaimStatus(str, Enum):
    OPEN = "OPEN"
    RESERVED_PENDING = "RESERVED_PENDING"
    ASSIGNED = "ASSIGNED"
    COMPLETED = "COMPLETED"


# ==============================================================================
# 2. RELATIONAL DATABASE MODELS (SQLAlchemy 2.0 Declarative ORM)
# ==============================================================================
class Base(DeclarativeBase):
    pass


class Project(Base):
    """Root thesis/research project card with 3-factor deduplication & anti-rewrite fingerprint."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lineage_dedup_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    publication_year: Mapped[int] = mapped_column(Integer, nullable=False, default=2026)
    department: Mapped[str] = mapped_column(
        String(120), nullable=False, default="Department of Computer Science & Engineering"
    )
    author_name: Mapped[str] = mapped_column(String(150), nullable=False, default="Unknown Author")
    supervisor_name: Mapped[str] = mapped_column(String(150), nullable=False, default="Faculty Advisor")

    domain_profile: Mapped[str] = mapped_column(
        String(48), nullable=False, default=DomainProfile.IT_AND_DATA_SCIENCE.value
    )
    modality: Mapped[str] = mapped_column(String(32), nullable=False, default=ModalityType.tabular.value)
    primary_language: Mapped[str] = mapped_column(String(32), nullable=False, default="Python")
    lifecycle_archetype: Mapped[str] = mapped_column(
        String(32), nullable=False, default=LifecycleArchetype.RELAY_CANDIDATE.value
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ProjectStatus.PROCESSING.value)
    final_handover_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))

    # 3-factor anti-rewrite & shift-immune fingerprint (< 4.5 KB per project, 0 MB extra RAM):
    minhash_signature: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)
    hard_anchors_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    hard_anchors_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    semantic_centroid_fp32: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    revisions: Mapped[list["ProjectRevision"]] = relationship(
        "ProjectRevision", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectRevision(Base):
    """Draft/Revision (v1, v2...) of a project containing the canonical CoreProjectSchema."""

    __tablename__ = "project_revisions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    pdf_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    pdf_blob_path: Mapped[str] = mapped_column(String(255), nullable=False)
    markdown_zst_path: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    passport_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    llm_audit_flags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    raw_code_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    raw_data_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    validity_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    horizon_component_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    time_decay_code: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=Decimal("1.000"))
    time_decay_data: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=Decimal("1.000"))
    gap_severity: Mapped[str] = mapped_column(String(16), nullable=False, default=GapSeverity.NONE.value)
    security_alert: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plagiarism_alert: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="revisions")
    artifact_probe: Mapped["ArtifactProbe | None"] = relationship(
        "ArtifactProbe", back_populates="revision", uselist=False, cascade="all, delete-orphan"
    )
    supply_items: Mapped[list["AtomicSupplyItem"]] = relationship(
        "AtomicSupplyItem", back_populates="revision", cascade="all, delete-orphan"
    )
    demand_items: Mapped[list["AtomicDemandItem"]] = relationship(
        "AtomicDemandItem", back_populates="revision", cascade="all, delete-orphan"
    )


class ArtifactProbe(Base):
    """Result of Module 2 (Automated Repository & External Dataset Verification)."""

    __tablename__ = "artifact_probes"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("project_revisions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    repo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    latest_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)

    repo_alive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_dependencies: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_clean_paths: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_data_artifact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_license: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    probe_status: Mapped[str] = mapped_column(
        String(32), default=ProbeStatus.NO_REPO_METHODOLOGY_ONLY.value, nullable=False
    )
    probe_diagnostics_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    probed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    revision: Mapped["ProjectRevision"] = relationship("ProjectRevision", back_populates="artifact_probe")


class ChapterExtractionCache(Base):
    """Chunk-level Content-Addressable Cache (SHA-256) saving 85% of LLM tokens on draft re-uploads."""

    __tablename__ = "chapter_extraction_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    zone_type: Mapped[str] = mapped_column(String(32), nullable=False, default=ZoneType.CORE_ENG.value)
    extracted_meat_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AtomicSupplyItem(Base):
    """Atomic reusable asset of a project (Supply: dataset, code_module, weights, methodology, legal_framework)."""

    __tablename__ = "atomic_supply_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("project_revisions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    item_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, default="dataset")
    domain_specific_text: Mapped[str] = mapped_column(Text, nullable=False)
    abstract_math_function: Mapped[str] = mapped_column(Text, nullable=False)
    operating_envelope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    effective_asset_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))

    revision: Mapped["ProjectRevision"] = relationship("ProjectRevision", back_populates="supply_items")


class AtomicDemandItem(Base):
    """Atomic unresolved R&D task / bottleneck (Demand: from Future Work or middle-chapter hidden stubs)."""

    __tablename__ = "atomic_demand_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("project_revisions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("bottleneck_clusters.id", ondelete="SET NULL"), index=True, nullable=True
    )
    item_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    macro_category: Mapped[str] = mapped_column(
        String(64), nullable=False, default=BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS.value
    )
    source_section: Mapped[str] = mapped_column(String(64), nullable=False, default="Future_Work")
    claim_status: Mapped[str] = mapped_column(String(32), nullable=False, default=ClaimStatus.OPEN.value)
    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    abstract_math_function: Mapped[str] = mapped_column(Text, nullable=False)
    operating_envelope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    revision: Mapped["ProjectRevision"] = relationship("ProjectRevision", back_populates="demand_items")


class RelayClaim(Base):
    """Task reservation by a next-generation student ('Take the Baton') with academic royalty contract."""

    __tablename__ = "relay_claims"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    demand_item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("atomic_demand_items.id", ondelete="CASCADE"), index=True, nullable=False
    )
    donor_supply_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("atomic_supply_items.id", ondelete="SET NULL"), nullable=True
    )
    follower_student_name: Mapped[str] = mapped_column(String(150), nullable=False)
    approving_supervisor_name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="APPROVED_ACTIVE")
    generated_package_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class BottleneckCluster(Base):
    """HDBSCAN micro-cluster of systemic university bottlenecks for the Dean's Treemap."""

    __tablename__ = "bottleneck_clusters"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    macro_category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    cluster_label: Mapped[str] = mapped_column(String(255), nullable=False)
    affected_projects_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    affected_departments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    medoid_vector_fp32: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    roi_recommendation_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ProjectLineageEdge(Base):
    """Directed edge in the Project Lineage Graph ('Git for Science': Gen 1 -> Gen 2 -> Gen 3)."""

    __tablename__ = "project_lineage_edges"
    __table_args__ = (UniqueConstraint("parent_project_id", "child_project_id", name="uq_lineage_parent_child"),)

    parent_project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    child_project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    inherited_asset_type: Mapped[str] = mapped_column(String(32), nullable=False, default="dataset")
    citation_contract_signed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class OutboxEvent(Base):
    """Transactional Outbox table ensuring eventual consistency between PostgreSQL and Qdrant."""

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, default="SYNC_REVISION_VECTORS")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FinOpsTokenLedger(Base):
    """Token consumption and USD cost ledger per pipeline stage."""

    __tablename__ = "finops_token_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("project_revisions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DomainModerationQueue(Base):
    """Quarantine queue for unknown external department domains awaiting 1-click approval."""

    __tablename__ = "domain_moderation_queue"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    sample_url: Mapped[str] = mapped_column(String(512), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    reviewed_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FailedJobDLQ(Base):
    """Dead Letter Queue for corrupted PDFs or unrecoverable pipeline errors."""

    __tablename__ = "failed_jobs_dlq"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    error_type: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    traceback_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ==============================================================================
# 3. PYDANTIC V2 SCHEMAS & DTOS
# ==============================================================================
class SecurityAlertDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    alert_code: str = "HIDDEN_TEXT_INJECTION_ATTEMPT"
    page_number: int
    hidden_char_count: int
    sample_snippet: str


class ChapterChunkDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chunk_index: int
    heading_title: str
    zone_type: ZoneType
    start_page: int
    end_page: int
    text_markdown: str
    token_estimate: int
    cache_key: str


class HarvestedDocumentDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: uuid.UUID
    revision_id: uuid.UUID
    pdf_sha256: str
    pdf_blob_path: str
    markdown_zst_path: str
    detected_title: str
    detected_author: str
    detected_supervisor: str
    detected_department: str
    detected_year: int
    detected_domain_profile: DomainProfile
    global_context_header: str
    header_hash: str
    extracted_urls: list[str] = Field(default_factory=list)
    lit_review_baselines: list[str] = Field(default_factory=list)
    claims_text: str = ""
    core_chunks: list[ChapterChunkDTO] = Field(default_factory=list)
    has_structured_appendix: bool = False
    minhash_signature: list[int] = Field(default_factory=list)
    hard_anchors: list[str] = Field(default_factory=list)
    hard_anchors_hash: str = ""
    security_alerts: list[SecurityAlertDTO] = Field(default_factory=list)
    total_pages: int = 0
    ocr_pages_count: int = 0


class HardSpecExtract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parameter_or_table: str
    exact_value_or_schema: str
    source_page: int = 1


class HiddenStubExtract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    component_or_step: str
    admission_quote: str
    technical_consequence: str
    source_page: int = 1


class DiscardedApproachExtract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    method: str
    failure_reason: str
    source_location: str
    source_page: int = 1


class EdgeCaseFailureExtract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    condition_or_class: str
    observed_degradation: str
    source_page: int = 1


class ChapterMeatSchema(BaseModel):
    """Structured output of the middle-chapter Map-Scan Worker."""
    model_config = ConfigDict(extra="ignore")

    chapter_heading: str = ""
    hard_specs: list[HardSpecExtract] = Field(default_factory=list)
    hidden_stubs: list[HiddenStubExtract] = Field(default_factory=list)
    discarded_approaches: list[DiscardedApproachExtract] = Field(default_factory=list)
    edge_case_failures: list[EdgeCaseFailureExtract] = Field(default_factory=list)


class ArtifactVerificationDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    repo_url: str | None = None
    latest_commit_sha: str | None = None
    repo_alive: bool = False
    has_dependencies: bool = False
    has_clean_paths: bool = False
    has_data_artifact: bool = False
    has_license: bool = False
    probe_status: ProbeStatus = ProbeStatus.NO_REPO_METHODOLOGY_ONLY
    detected_stack: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class OperatingEnvelopeSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    domain_env: DomainEnvType = DomainEnvType.pure_software_cloud
    compatible_envs: list[DomainEnvType] = Field(
        default_factory=lambda: [DomainEnvType.pure_software_cloud]
    )
    io_signature: str = "structured_table -> analytical_output"
    hard_preconditions: list[str] = Field(default_factory=list)


class AtomicSupplySchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str | None = None
    asset_type: str = Field(
        default="dataset",
        description="dataset | code_module | weights | methodology | legal_framework | empirical_corpus | blueprint",
    )
    domain_specific_text: str
    abstract_math_function: str = Field(
        description="Domain-agnostic TRIZ mathematical/structural transformation without domain jargon"
    )
    operating_envelope: OperatingEnvelopeSchema = Field(default_factory=OperatingEnvelopeSchema)


class AtomicDemandSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str | None = None
    source: str = "Future_Work_Section"
    macro_category: BottleneckMacroCategory = BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS
    claim_status: ClaimStatus = ClaimStatus.OPEN
    task_description: str
    abstract_math_function: str = Field(
        description="Domain-agnostic TRIZ mathematical/structural requirement without domain jargon"
    )
    operating_envelope: OperatingEnvelopeSchema = Field(default_factory=OperatingEnvelopeSchema)
    source_page: int = 1


class FutureWorkLinterItem(BaseModel):
    """Item for the Split-View Diff Linter of the Future Work section."""
    model_config = ConfigDict(extra="ignore")

    original_sentence: str
    verdict: str = Field(description="FLUFF | WEAK_SPECIFICITY | ACTIONABLE_RD")
    reason_badge: str
    points_impact: int = 0


class RealityVsConclusionGapSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conclusion_claim: str
    middle_chapter_reality: str
    gap_severity: GapSeverity = GapSeverity.LOW
    source_page: int = 1


class PriorArtProjectRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str
    title: str
    year: int
    department: str = ""
    author: str = ""
    similarity_score: float = 0.0
    similarity_note: str


class PriorArtRadarSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    similar_past_projects: list[PriorArtProjectRef] = Field(default_factory=list)


class DeepHarvestAuditSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reality_vs_conclusion_gap: RealityVsConclusionGapSchema
    commission_defense_questions: list[str] = Field(default_factory=list)
    prior_art_radar: PriorArtRadarSchema = Field(default_factory=PriorArtRadarSchema)
    discarded_approaches: list[DiscardedApproachExtract] = Field(default_factory=list)
    future_work_linter_items: list[FutureWorkLinterItem] = Field(default_factory=list)


class SupplyAssetsSectionSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code_summary: str
    data_summary: str
    atomic_supply_items: list[AtomicSupplySchema] = Field(default_factory=list)


class DemandHorizonSectionSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bottleneck_macro_category: BottleneckMacroCategory = BottleneckMacroCategory.ALGORITHMIC_LIMITATIONS
    bottleneck_cluster_label: str = "General Technical Bottleneck"
    filtered_fluff_items: list[str] = Field(default_factory=list)
    atomic_demand_items: list[AtomicDemandSchema] = Field(default_factory=list)


class LLMAuditFlagsSchema(BaseModel):
    """Binary audit flags (LLM answers ONLY these objective flags; never assigns numerical scores)."""
    model_config = ConfigDict(extra="ignore")

    has_software_code: bool = True
    is_unique_primary_dataset: bool = False
    has_baseline_and_split: bool = False
    suspect_data_leakage: bool = False
    has_target_metric_in_roadmap: bool = False
    has_concrete_method_in_roadmap: bool = False
    is_fully_completed_gold_standard: bool = False
    has_structured_appendix: bool = False
    has_reproducible_methodology: bool = False


class ScoringBreakdownSchema(BaseModel):
    """Output of Module 4 (Deterministic Mathematical Handover Scorer)."""
    model_config = ConfigDict(extra="ignore")

    scoring_mode: str = "SOFTWARE_CODE_AND_DATA"
    raw_code_score: int = 0
    raw_data_score: int = 0
    validity_score: int = 0
    roadmap_or_maturity_score: int = 0
    time_decay_code: float = 1.0
    time_decay_data: float = 1.0
    final_handover_score: float = 0.0
    status: str = "Relay Candidate"
    improvement_recipes: list[str] = Field(default_factory=list)


class ProjectMetaSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    year: int = 2026
    department: str = "Department of Computer Science & Engineering"
    author: str = "Thesis Author"
    supervisor: str = "Faculty Advisor"
    domain_profile: DomainProfile = DomainProfile.IT_AND_DATA_SCIENCE
    modality: ModalityType = ModalityType.tabular
    primary_language: str = "Python"
    frameworks: list[str] = Field(default_factory=list)


class LineageInfoSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    generation: int = 1
    forked_from_project_id: str | None = None
    inherited_asset_type: str | None = None
    citation_contract_active: bool = True


class LLMExtractionOutputSchema(BaseModel):
    """Strict output schema for the Cross-Check Reducer (Module 3). No scoring field allowed."""
    model_config = ConfigDict(extra="ignore")

    lifecycle_archetype: LifecycleArchetype = LifecycleArchetype.RELAY_CANDIDATE
    meta: ProjectMetaSchema
    deep_harvest_audit: DeepHarvestAuditSchema
    supply_assets: SupplyAssetsSectionSchema
    demand_horizon: DemandHorizonSectionSchema
    llm_audit_flags: LLMAuditFlagsSchema


class CoreProjectSchema(BaseModel):
    """Canonical JSON project passport stored in project_revisions.passport_json."""
    model_config = ConfigDict(extra="ignore")

    project_id: str
    revision_id: str | None = None
    revision_number: int = 1
    lifecycle_archetype: LifecycleArchetype = LifecycleArchetype.RELAY_CANDIDATE
    security_alert: str | None = None
    plagiarism_alert: str | None = None
    lineage: LineageInfoSchema = Field(default_factory=LineageInfoSchema)
    meta: ProjectMetaSchema
    artifact_verification: ArtifactVerificationDTO
    deep_harvest_audit: DeepHarvestAuditSchema
    supply_assets: SupplyAssetsSectionSchema
    demand_horizon: DemandHorizonSectionSchema
    llm_audit_flags: LLMAuditFlagsSchema
    scoring: ScoringBreakdownSchema


# ==============================================================================
# 4. API CONTRACT DTOS
# ==============================================================================
class SynergyFormulaBreakdownDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    synergy_score: float
    p_rerank_calibrated: float
    cosine_similarity: float
    m_envelope: float
    m_stack: float
    donor_effective_asset_score: float
    compatibility_verdict: str


class SynergyBridgeDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bridge_id: str
    demand_item_id: str
    demand_task_description: str
    demand_abstract_math: str
    donor_project_id: str
    donor_supply_item_id: str
    donor_title: str
    donor_department: str
    donor_author: str
    donor_year: int
    donor_domain_profile: str
    donor_asset_type: str
    donor_supply_text: str
    donor_abstract_math: str
    donor_repo_url: str | None = None
    formula: SynergyFormulaBreakdownDTO


class ExternalFallbackAssetDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    demand_item_id: str
    source_platform: str = "HuggingFace Hub"
    external_id: str
    title: str
    url: str
    downloads_or_stars: int = 0
    description: str = ""
    match_reason: str = ""


class SynergyGraphDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str
    revision_number: int = 1
    internal_matches: list[SynergyBridgeDTO] = Field(default_factory=list)
    external_fallbacks: list[ExternalFallbackAssetDTO] = Field(default_factory=list)
    external_radar_status: str = "online"


class LineageNodeDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str
    title: str
    author: str
    supervisor: str
    year: int
    department: str
    final_handover_score: float
    lifecycle_archetype: str
    generation: int = 1


class LineageEdgeDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parent_project_id: str
    child_project_id: str
    inherited_asset_type: str
    citation_contract_signed: bool = True


class LineageGraphDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    root_project_id: str
    nodes: list[LineageNodeDTO] = Field(default_factory=list)
    edges: list[LineageEdgeDTO] = Field(default_factory=list)


class TakeBatonRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    demand_item_id: uuid.UUID
    donor_supply_item_id: uuid.UUID | None = None
    follower_student_name: str = Field(min_length=2, max_length=150)
    approving_supervisor_name: str = Field(min_length=2, max_length=150)
    new_project_title: str | None = None
    accept_citation_contract: bool = True


class PackageGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    donor_project_id: uuid.UUID | None = None
    donor_supply_item_id: uuid.UUID | None = None
    demand_item_id: uuid.UUID | None = None
    follower_student_name: str = "Next-Gen R&D Fellow (Cohort 2026/2027)"


class HandoverPackageDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str
    handover_passport_md: str
    citation_cff: str
    synergy_merge_spec_md: str | None = None


class ClusterNodeDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cluster_id: str
    cluster_label: str
    macro_category: str
    affected_projects_count: int
    affected_departments_count: int
    departments_list: list[str] = Field(default_factory=list)
    supervisors_list: list[str] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
    project_titles: list[str] = Field(default_factory=list)
    estimated_unlock_roi: str = ""
    recommended_action: str = ""


class MacroCategoryTreeDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    macro_category: str
    total_projects_blocked: int
    clusters: list[ClusterNodeDTO] = Field(default_factory=list)


class GoldenReserveBubbleDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str
    title: str
    department: str
    author: str
    supervisor: str
    year: int
    domain_profile: str
    lifecycle_archetype: str
    asset_value_x: float
    horizon_score_y: float
    final_handover_score: float
    has_active_followers: bool = False
    is_pure_supply_donor: bool = False


class DeanAnalyticsResponseDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_projects: int
    relay_candidates_count: int
    gold_standard_trl_count: int
    total_clusters_count: int
    emerging_unclassified_count: int
    daily_finops_spend_usd: float
    daily_finops_budget_usd: float
    treemap_hierarchy: list[MacroCategoryTreeDTO] = Field(default_factory=list)
    golden_reserve_matrix: list[GoldenReserveBubbleDTO] = Field(default_factory=list)
    trl_showcase_projects: list[GoldenReserveBubbleDTO] = Field(default_factory=list)
    pending_domains: list[dict[str, Any]] = Field(default_factory=list)


class DeanActionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_type: str = Field(
        default="export_vkr_bank",
        description="export_vkr_bank | export_grant_justification | approve_domain | trigger_reclustering",
    )
    project_ids: list[uuid.UUID] = Field(default_factory=list)
    cluster_id: uuid.UUID | None = None
    domain_id: uuid.UUID | None = None
    academic_year_target: str = "2026/2027"
    reviewer_name: str = "Dean's Office / R&D Committee"
