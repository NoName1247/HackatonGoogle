"""
[1] Конфигурация системы, пул соединений PostgreSQL 16 (asyncpg),
двухконтурные клиенты к единому Redis (db=0 state / db=1 cache),
инициализация 3 коллекций Qdrant, распределенный Circuit Breaker,
FinOps предохранитель и CAS-менеджер блобов (PDF + zstd Markdown).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, AsyncGenerator

import orjson
import redis.asyncio as aioredis
import zstandard as zstd
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from qdrant_client import AsyncQdrantClient, QdrantClient, models
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool

logger = logging.getLogger("horizon.config")

# Фиксированное пространство имен для детерминированной генерации UUIDv5 (идемпотентность Qdrant и БД)
NAMESPACE_HORIZON = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
PROMPT_VERSION = "v2.1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "production"
    SECRET_KEY: str = "horizon-relay-super-secret-jwt-key-2026-univ-audit"
    CURRENT_ACADEMIC_YEAR: int = 2026

    # PostgreSQL 16 (прямое подключение с пулом в процессе)
    DATABASE_URL: str = "postgresql+asyncpg://horizon:horizon_secure_pwd@postgres:5432/horizon_relay"
    DB_POOL_SIZE: int = 8
    DB_MAX_OVERFLOW: int = 8

    # Единый контейнер Redis с разделением логических БД:
    # db=0 (State: очереди Celery, Redis Streams SSE, локи, Rate-Limit — без TTL)
    # db=1 (Cache: L2 кэш синергии, GitHub Probe и LLM Gate — всегда с TTL)
    REDIS_STATE_URL: str = "redis://redis:6379/0"
    REDIS_CACHE_URL: str = "redis://redis:6379/1"

    # Qdrant Vector DB
    QDRANT_HOST: str = "qdrant"
    QDRANT_HTTP_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334

    # Локальное контентно-адресуемое хранилище (CAS)
    BLOB_STORAGE_DIR: Path = Field(default=Path("/var/lib/horizon/blobs"))

    # LLM API ключи (LiteLLM)
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Пул GitHub PAT токенов и белый список доменов
    GITHUB_PAT_POOL: str = ""
    AUTO_ALLOWLIST_DOMAINS: str = (
        "github.com,gitlab.com,huggingface.co,zenodo.org,kaggle.com,osf.io,figshare.com,data.mendeley.com"
    )

    # FinOps и квоты DAG
    DAILY_LLM_BUDGET_USD: float = 1.50
    MAX_PAGES_PROCESSED: int = 150
    MAX_MAP_CHUNKS_PER_THESIS: int = 10
    MAX_TOTAL_TOKENS_PER_JOB: int = 55000
    ONNX_MAX_CONCURRENT: int = 2

    @property
    def allowlist_domains_set(self) -> set[str]:
        return {
            d.strip().lower()
            for d in self.AUTO_ALLOWLIST_DOMAINS.split(",")
            if d.strip()
        }

    @property
    def github_tokens_list(self) -> list[str]:
        return [
            t.strip()
            for t in self.GITHUB_PAT_POOL.split(",")
            if t.strip()
        ]


settings = Settings()


def deterministic_uuid5(namespace_tag: str, *parts: Any) -> uuid.UUID:
    """
    Генерирует детерминированный UUIDv5 для атомарных элементов SUPPLY/DEMAND и точек Qdrant.
    Гарантирует Effectively-Once семантику при повторных запусках Outbox.
    """
    raw_name = f"{namespace_tag}:" + ":".join(str(p) for p in parts)
    return uuid.uuid5(NAMESPACE_HORIZON, raw_name)


# ==============================================================================
# ПУЛ СОЕДИНЕНИЙ POSTGRESQL 16 (SQLAlchemy 2.0 Async)
# ==============================================================================
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency для получения асинхронной сессии БД."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def db_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Контекстный менеджер сессии БД для фоновых воркеров Celery."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ==============================================================================
# КЛИЕНТЫ REDIS (DB=0 STATE & DB=1 CACHE)
# ==============================================================================
_redis_state_pool: aioredis.Redis | None = None
_redis_cache_pool: aioredis.Redis | None = None


def get_redis_state() -> aioredis.Redis:
    """
    Возвращает клиент к логической базе db=0 (State: стримы SSE, блокировки, Rate-Limit, Circuit Breaker).
    Ключи без TTL в db=0 никогда не вытесняются политикой volatile-lfu.
    """
    global _redis_state_pool
    if _redis_state_pool is None:
        _redis_state_pool = aioredis.from_url(
            settings.REDIS_STATE_URL,
            decode_responses=False,
            max_connections=40,
            socket_timeout=5.0,
            socket_connect_timeout=2.0,
        )
    return _redis_state_pool


def get_redis_cache() -> aioredis.Redis:
    """
    Возвращает клиент к логической базе db=1 (L2 Cache: синергия, проверка репо, LLM Gate).
    Все ключи здесь создаются строго с SETEX / EXPIRE и автоматически ротируются по LFU.
    """
    global _redis_cache_pool
    if _redis_cache_pool is None:
        _redis_cache_pool = aioredis.from_url(
            settings.REDIS_CACHE_URL,
            decode_responses=False,
            max_connections=30,
            socket_timeout=3.0,
            socket_connect_timeout=2.0,
        )
    return _redis_cache_pool


# ==============================================================================
# ВЕКТОРНОЕ ЯДРО QDRANT (3 КОЛЛЕКЦИИ В FP32 RAM: SUPPLY, DEMAND, EVIDENCE)
# ==============================================================================
QDRANT_COLLECTIONS = (
    "supply_vectors",
    "demand_vectors",
    "evidence_and_dead_ends",
)

_qdrant_async_client: AsyncQdrantClient | None = None
_qdrant_sync_client: QdrantClient | None = None


def get_async_qdrant() -> AsyncQdrantClient:
    """Асинхронный gRPC-клиент Qdrant для FastAPI и асинхронных функций."""
    global _qdrant_async_client
    if _qdrant_async_client is None:
        _qdrant_async_client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_HTTP_PORT,
            grpc_port=settings.QDRANT_GRPC_PORT,
            prefer_grpc=False, check_compatibility=False,
            timeout=10,
        )
    return _qdrant_async_client


def get_sync_qdrant() -> QdrantClient:
    """Синхронный gRPC-клиент Qdrant для инициализации и синхронных задач Celery."""
    global _qdrant_sync_client
    if _qdrant_sync_client is None:
        _qdrant_sync_client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_HTTP_PORT,
            grpc_port=settings.QDRANT_GRPC_PORT,
            prefer_grpc=False, check_compatibility=False,
            timeout=10,
        )
    return _qdrant_sync_client


async def init_qdrant_collections() -> None:
    """
    Создает 3 изолированные коллекции в Qdrant (supply_vectors, demand_vectors, evidence_and_dead_ends)
    с поддержкой гибридного поиска (Named Vectors: dense 1024d FP32 + sparse BM25)
    и индексами Payload для предфильтрации до обхода графа HNSW.
    """
    client = get_async_qdrant()
    for col_name in QDRANT_COLLECTIONS:
        exists = await client.collection_exists(col_name)
        if not exists:
            logger.info("Creating Qdrant collection '%s' (FP32 in RAM + Sparse BM25)...", col_name)
            await client.create_collection(
                collection_name=col_name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=1024,
                        distance=models.Distance.COSINE,
                        on_disk=False,
                        hnsw_config=models.HnswConfigDiff(
                            m=16,
                            ef_construct=128,
                            full_scan_threshold=5000,
                        ),
                    )
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=False)
                    )
                },
            )
            # Индексы Payload для мгновенной предфильтрации (Filterable HNSW)
            await client.create_payload_index(col_name, "project_id", models.PayloadSchemaType.UUID)
            await client.create_payload_index(col_name, "revision_number", models.PayloadSchemaType.INTEGER)
            await client.create_payload_index(col_name, "modality", models.PayloadSchemaType.KEYWORD)
            await client.create_payload_index(col_name, "domain_env", models.PayloadSchemaType.KEYWORD)
            await client.create_payload_index(col_name, "domain_profile", models.PayloadSchemaType.KEYWORD)
            await client.create_payload_index(col_name, "primary_language", models.PayloadSchemaType.KEYWORD)
            await client.create_payload_index(col_name, "has_data_artifact", models.PayloadSchemaType.BOOL)
            await client.create_payload_index(col_name, "effective_asset_score", models.PayloadSchemaType.FLOAT)
            if col_name == "evidence_and_dead_ends":
                await client.create_payload_index(col_name, "chunk_type", models.PayloadSchemaType.KEYWORD)


async def init_postgres_schema() -> None:
    """
    Инициализирует расширения PostgreSQL (uuid-ossp, pg_trgm), создает все таблицы ORM
    и специализированные GIN/Covering/Partial индексы из Модуля 4.
    """
    from models_and_schemas import Base

    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pg_trgm";'))
        await conn.run_sync(Base.metadata.create_all)

        # Специализированные индексы производительности (Модуль 4.1.А)
        ddl_statements = [
            """
            CREATE INDEX IF NOT EXISTS idx_projects_title_trgm
            ON projects USING GIN (title gin_trgm_ops);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_projects_relay_board
            ON projects (modality, primary_language, final_handover_score DESC)
            INCLUDE (id, title, department, publication_year, lifecycle_archetype, domain_profile)
            WHERE status = 'COMPLETED';
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_revisions_passport_gin
            ON project_revisions USING GIN (passport_json jsonb_path_ops);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_outbox_pending_poll
            ON outbox_events (next_retry_at ASC, id ASC)
            WHERE status = 'PENDING';
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_finops_daily_spend
            ON finops_token_ledger (recorded_at DESC) INCLUDE (cost_usd);
            """,
        ]
        for stmt in ddl_statements:
            await conn.execute(text(stmt))


# ==============================================================================
# РАСПРЕДЕЛЕННЫЙ CIRCUIT BREAKER В REDIS (CLOSED -> OPEN -> HALF_OPEN)
# ==============================================================================
class DistributedCircuitBreaker:
    """
    Синхронизированный через Redis конечный автомат защиты от каскадных сбоев
    внешних узлов (Gemini API, OpenAI API, GitHub API, HuggingFace Hub API).
    """

    def __init__(self, service_name: str, failure_threshold: int = 4, window_sec: int = 30, cooldown_sec: int = 45):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.window_sec = window_sec
        self.cooldown_sec = cooldown_sec
        self.key_open = f"cb:open:{service_name}"
        self.key_fails = f"cb:fails:{service_name}"

    async def is_available(self) -> bool:
        """Возвращает True, если цепь замкнута (CLOSED) или готова к пробному вызову (HALF_OPEN)."""
        r = get_redis_state()
        open_until = await r.get(self.key_open)
        if open_until is None:
            return True
        if float(open_until.decode()) <= time.time():
            await r.delete(self.key_open)
            return True
        return False

    async def record_success(self) -> None:
        """Сбрасывает счетчик ошибок после успешного ответа."""
        r = get_redis_state()
        await r.delete(self.key_fails, self.key_open)

    async def record_failure(self, custom_cooldown: int | None = None) -> bool:
        """
        Фиксирует ошибку. Если превышен порог за окно времени — размыкает цепь (OPEN)
        и возвращает True.
        """
        r = get_redis_state()
        fails = await r.incr(self.key_fails)
        if fails == 1:
            await r.expire(self.key_fails, self.window_sec)
        if fails >= self.failure_threshold:
            cd = custom_cooldown or self.cooldown_sec
            open_until = time.time() + cd
            await r.setex(self.key_open, cd + 5, str(open_until))
            logger.warning("CircuitBreaker OPENED for '%s' for %ds (fails=%d)", self.service_name, cd, fails)
            return True
        return False


# ==============================================================================
# КОНТРОЛЛЕР БЮДЖЕТА FINOPS (<= $50/мес, дневной предохранитель $1.50/день)
# ==============================================================================
class FinOpsBudgetTracker:
    """
    Отслеживает расход токенов и средств в реальном времени (Redis + таблица finops_token_ledger).
    При превышении дневного лимита включает Hard FinOps Quota Breaker.
    """

    # Тарифы за 1M токенов (USD)
    MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
        "gemini-2.5-flash": (0.15, 0.60),
        "gemini/gemini-2.5-flash": (0.15, 0.60),
        "gpt-4o-mini": (0.15, 0.60),
        "openai/gpt-4o-mini": (0.15, 0.60),
        "gemini-2.5-pro": (1.25, 5.00),
        "gpt-4o": (2.50, 10.00),
    }

    @staticmethod
    def _today_key() -> str:
        day_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"finops:daily_spend_usd:{day_str}"

    @classmethod
    def calculate_cost_usd(cls, model_name: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
        in_rate, out_rate = cls.MODEL_PRICING_PER_1M.get(model_name, (0.15, 0.60))
        cost = (prompt_tokens / 1_000_000.0) * in_rate + (completion_tokens / 1_000_000.0) * out_rate
        return Decimal(f"{cost:.6f}")

    @classmethod
    async def can_spend_llm_tokens(cls) -> bool:
        """Проверяет, не превышен ли дневной бюджет FinOps ($1.50)."""
        r = get_redis_state()
        raw_val = await r.get(cls._today_key())
        if raw_val is None:
            return True
        return float(raw_val.decode()) < settings.DAILY_LLM_BUDGET_USD

    @classmethod
    async def get_today_spend_usd(cls) -> float:
        r = get_redis_state()
        raw_val = await r.get(cls._today_key())
        return round(float(raw_val.decode()), 4) if raw_val else 0.0

    @classmethod
    async def record_llm_usage(
        cls,
        session: AsyncSession | None,
        revision_id: uuid.UUID | None,
        stage: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> Decimal:
        """Атомарно увеличивает счетчик в Redis и пишет строку в finops_token_ledger."""
        from models_and_schemas import FinOpsTokenLedger

        cost_usd = cls.calculate_cost_usd(model_name, prompt_tokens, completion_tokens)
        r = get_redis_state()
        key = cls._today_key()
        await r.incrbyfloat(key, float(cost_usd))
        await r.expire(key, 172800)  # 48 часов хранения оперативного счетчика

        if session is not None and revision_id is not None:
            ledger_entry = FinOpsTokenLedger(
                revision_id=revision_id,
                stage=stage,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
            )
            session.add(ledger_entry)
        return cost_usd


# ==============================================================================
# КОНТЕНТНО-АДРЕСУЕМОЕ ХРАНИЛИЩЕ БЛОБОВ (CAS: PDF + ZSTD MARKDOWN)
# ==============================================================================
class CASStorageManager:
    """
    Управляет сохранением PDF и сжатых алгоритмом Zstandard (.md.zst) слепков Markdown на NVMe.
    Не удерживает развернутые тексты дипломов в оперативной памяти.
    """

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or settings.BLOB_STORAGE_DIR
        self.pdf_dir = self.base_dir / "pdf"
        self.md_dir = self.base_dir / "md"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.md_dir.mkdir(parents=True, exist_ok=True)
        self._compressor = zstd.ZstdCompressor(level=6)
        self._decompressor = zstd.ZstdDecompressor()

    def save_pdf_bytes(self, pdf_bytes: bytes, sha256_hex: str | None = None) -> tuple[str, str]:
        """Сохраняет PDF по его SHA-256 хэшу. Возвращает (sha256_hex, pdf_blob_path)."""
        digest = sha256_hex or hashlib.sha256(pdf_bytes).hexdigest()
        target_path = self.pdf_dir / f"{digest}.pdf"
        if not target_path.exists():
            target_path.write_bytes(pdf_bytes)
        return digest, str(target_path)

    def save_compressed_markdown(self, revision_id: uuid.UUID, markdown_text: str) -> str:
        """Сжимает извлеченный Markdown с таблицами в 5–6 раз через zstd и записывает на диск."""
        target_path = self.md_dir / f"{revision_id}.md.zst"
        compressed = self._compressor.compress(markdown_text.encode("utf-8"))
        target_path.write_bytes(compressed)
        return str(target_path)

    def load_compressed_markdown(self, zst_path: str | Path) -> str:
        """Распаковывает Markdown-слепок с диска только при прямом запросе."""
        p = Path(zst_path)
        if not p.exists():
            return ""
        raw_bytes = self._decompressor.decompress(p.read_bytes())
        return raw_bytes.decode("utf-8", errors="replace")


cas_storage = CASStorageManager()


# ==============================================================================
# ВСПОМОГАТЕЛЬНАЯ ПУБЛИКАЦИЯ СОБЫТИЙ В REDIS STREAMS (ДЛЯ SSE И POLLING)
# ==============================================================================
async def publish_job_stream_event(
    job_id: str | uuid.UUID,
    event_type: str,
    step: int,
    percent: int,
    title: str,
    payload: dict[str, Any] | None = None,
) -> str:
    """
    Записывает событие прогресса пайплайна в Redis Stream `stream:job:{job_id}` через XADD.
    Гарантирует, что браузер получит все события с шага 1 даже при позднем подключении или реконнекте.
    """
    r = get_redis_state()
    stream_key = f"stream:job:{job_id}"
    data_dict = {
        "job_id": str(job_id),
        "event": event_type,
        "step": step,
        "percent": percent,
        "title": title,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }
    entry_id = await r.xadd(
        stream_key,
        {"event": event_type.encode("utf-8"), "data": orjson.dumps(data_dict)},
        maxlen=100,
        approximate=True,
    )
    # Храним историю стрима задачи 2 часа
    await r.expire(stream_key, 7200)
    return entry_id.decode("utf-8") if isinstance(entry_id, bytes) else str(entry_id)

