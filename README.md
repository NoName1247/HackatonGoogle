# Horizon Relay

Zero-Trust Academic Thesis Audit & Asymmetric R&D Synergy Engine.

Horizon Relay принимает диплом/диссертацию (PDF + опционально ссылку на репозиторий), прогоняет его через пайплайн аудита (извлечение структуры, проверка внешних артефактов, LLM-скоринг, построение графа «супply/demand»), и даёт трём ролям разные инструменты:

- **Комиссия** — рентген-досье проекта: оценка, разрывы между выводами и реальными результатами, вопросы к защите, prior-art радар, верификация репозитория.
- **Студент** — маркетплейс «эстафеты»: можно забрать незакрытую задачу из чужого диплома (supply/demand матчинг), получить handover-пакет, посмотреть граф происхождения (lineage).
- **Деканат** — аналитика по кафедре: узкие места (treemap), «золотой резерв» готовых к продолжению тем, TRL 6-7 кандидаты на индустрию/патентование, экспорт банка тем, модерация доменов, FinOps по расходам на LLM.

## Архитектура

```
                    ┌────────┐
                    │ nginx  │  :8080 → :80
                    └───┬────┘
              ┌─────────┴─────────┐
              ▼                   ▼
      ┌───────────────┐   ┌───────────────┐
      │ frontend       │   │ api (FastAPI) │
      │ Next.js 14     │   │ /api/v1/*     │
      └───────────────┘   └───────┬───────┘
                                   │
          ┌────────────┬──────────┼───────────┬─────────────┐
          ▼            ▼          ▼           ▼             ▼
     worker-parser worker-probe worker-auditor worker-synergy worker-cron
     (q_parser)    (q_probe)    (q_auditor)    (q_synergy)   (q_cron+beat)
          │            │          │           │             │
          └────────────┴──────────┴───────────┴─────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
               PostgreSQL 16    Redis 7.2       Qdrant v1.12
               (данные)      (очереди/кэш/SSE)  (векторный поиск)
```

Все 5 Celery-воркеров и API-сервис собираются из одного Docker-образа `horizon-relay-backend` — различается только команда запуска.

## Функции Backend (FastAPI + Celery, `backend/`)

### API, `backend/main_api.py` (префикс `/api/v1`)

| Метод | Путь | Что делает |
|---|---|---|
| `POST` | `/projects/ingest` | Загрузка PDF диплома (multipart, до 25 МБ, проверка magic bytes `%PDF-`), дедуп по SHA-256, создаёт `Project`, ставит задачу в `q_parser`. Возвращает `job_id` и SSE-URL. |
| `GET` | `/jobs/{job_id}/stream` | SSE-поток прогресса пайплайна (Redis Streams `XREAD`, resumable через `Last-Event-ID`). `?fallback=poll` — обычный поллинг JSON для сетей, где SSE блокируется. |
| `GET` | `/projects` | Каталог завершённых проектов: фильтры `modality`, `language`, `department`, `domain_profile`, `archetype`, `min_score`, `has_dataset`, полнотекстовый `q`, `limit`. |
| `GET` | `/projects/{project_id}` | Полное досье: паспорт, атомарные supply/demand items, граф lineage. |
| `GET` | `/projects/{project_id}/synergy` | Асимметричный supply/demand матчинг («Synergy Bridge»); опциональный `bounty_query` — матчинг под внешний текст корпоративного заказа. Кэш 2ч, защита от cache-stampede через Redis SingleFlight-лок. |
| `POST` | `/projects/{project_id}/claim` | «Взять эстафету»: студент резервирует открытую задачу (`SELECT...FOR UPDATE NOWAIT`, конкурентные заявки получают 409). |
| `POST` | `/projects/{project_id}/package` | Генерация handover-пакета: `HANDOVER_PASSPORT.md`, `CITATION.cff`, synergy merge-spec. |
| `GET` | `/analytics/bottlenecks` | Данные дашборда деканата: treemap узких мест, Golden Reserve, TRL 6-7, FinOps. Фильтры `year`, `department`. |
| `POST` | `/analytics/export-topics` | Действия деканата: `export_vkr_bank`, `export_grant_justification`, `approve_domain`, `trigger_reclustering`. |

Rate-limit — Redis Lua token-bucket, 3 зоны (Ingest / External_Match / Read). Аутентификации нет (поле `SECRET_KEY` зарезервировано, но ни одного защищённого роута нет), CORS открыт полностью — не готово для публичного прода без доработки.

### Пайплайн обработки (`backend/core/`)

| Модуль | Что делает | Воркер / очередь |
|---|---|---|
| `harvester.py` | Глубокий парсинг PDF (PyMuPDF4LLM), защита от decompression-bomb и скрытого текста, OCR сканов (RapidOCR/ONNX), склейка таблиц между страницами, разметка на зоны (литобзор/инженерное ядро/выводы), чанкинг, MinHash/anchor/centroid-фингерпринт для дедупа и анти-рефразинга. | `worker-parser` / `q_parser` |
| `artifact_probe.py` | Проверка внешних репозиториев/датасетов (GitHub, GitLab, HuggingFace, Zenodo, OSF) через API без клонирования; защита от SSRF/DNS-rebinding, ротация пула GitHub PAT. | `worker-probe` / `q_probe` |
| `auditor_and_scorer.py` | LLM-экстракция структуры диплома (LiteLLM: Gemini/OpenAI, либо детерминированный fallback без LLM-ключей) + формула итогового handover-скора. | `worker-auditor` / `q_auditor` |
| `synergy_engine.py` | Эмбеддинги supply/demand (ONNX: BAAI/bge-m3 + bm25-sparse + bge-reranker-v2-m3) в Qdrant, prior-art/novelty поиск, 4-шаговый асимметричный матчер с LLM feasibility gate. | `worker-synergy` / `q_synergy` |
| `ontology_and_roi.py` | Иерархическая онтология узких мест, HDBSCAN-кластеризация нерешённых задач, агрегация ROI-дашборда деканата, выполнение действий деканата. | `worker-cron`, `worker-synergy`, API |
| `lineage_packager.py` | Рекурсивный обход графа происхождения проектов («Git for Science»), локинг заявок на эстафету, генерация `HANDOVER_PASSPORT.md`/`CITATION.cff`/merge-spec через Jinja2. | вызывается напрямую из API |

Celery (`backend/workers/celery_app.py`): брокер/backend — Redis db=0, очереди `q_parser`/`q_probe`/`q_auditor`/`q_synergy`/`q_cron`, JSON-сериализация, `task_acks_late`, DLQ при сбое (карантин проекта + запись в `FailedJobDLQ`). Celery Beat: реконсиляция outbox каждые 15с, повтор проб GitHub каждые 15 мин, ночная HDBSCAN-переклайстеризация и time-decay в 03:00 UTC.

### Данные (`backend/models_and_schemas.py`)

SQLAlchemy 2.0 async ORM, без Alembic (схема создаётся `create_all` + ручной DDL индексов при старте API). Ключевые таблицы: `Project`, `ProjectRevision` (версии паспорта), `ArtifactProbe`, `ChapterExtractionCache`, `AtomicSupplyItem`/`AtomicDemandItem`, `RelayClaim`, `BottleneckCluster`, `ProjectLineageEdge`, `OutboxEvent`, `FinOpsTokenLedger`, `DomainModerationQueue`, `FailedJobDLQ`.

При пустой таблице `projects` API автоматически сидит demo-данные (`backend/scripts/seed_demo_data.py`, ~200 демо-проектов) при старте.

## Функции Frontend (Next.js 14, `frontend/`)

Дизайн-система — кастомные CSS-токены (`.card`/`.chip`/`.seg`/`.bento`/`ScoreRing`) в `src/app/globals.css`. Один общий zustand-store `useHorizonStore` (`src/lib/store.ts`) держит состояние загрузки/SSE, активный проект, фильтры маркетплейса и выбор деканата. Все обращения к API — через `src/lib/api_and_sse.ts` (база — `NEXT_PUBLIC_API_URL`, по умолчанию `/api/v1`).

### `/` — Комиссия: загрузка

Загрузка PDF диплома (+ опционально ссылка на репозиторий и заголовок), кнопка «демо в 1 клик» (генерирует валидный PDF прямо в браузере, без выбора файла), либо выбор уже обработанного проекта из каталога. Во время обработки — экран с прогрессом 6 шагов пайплайна (SSE `/jobs/{id}/stream`, с поллинг-фоллбеком). После завершения — автопереход на `/dossier`.

### `/dossier?tab=...` — Комиссия: рентген-досье

- **passport** — ScoreRing с `final_handover_score`, разбивка по 4 осям (код/методология, данные, валидность, зрелость roadmap), алерты безопасности/плагиата, сводка supply/demand.
- **questions** — AI-сгенерированные вопросы к защите на основе разрыва между выводами и реальными результатами.
- **reality** — «заявлено в выводах» vs «что реально показано в главах 2-3»: severity-метка, «future work линтер» (FLUFF/WEAK_SPECIFICITY), список отклонённых подходов («не повторять»).
- **prior-art** — радар похожих работ за 5 лет по другим кафедрам с % схожести.
- **supply-demand** — карточки извлекаемых активов (supply) и открытых задач (demand), плюс до 3 готовых решений из других кафедр под узкие места этого проекта.
- **verification** — 5 автоматических проверок репозитория (жив, зависимости, чистые пути, не LFS-заглушка, открытая лицензия) + статус пробы + стек технологий.
- **lineage** — граф поколений проекта («Git for Science»), рендерится `SynergyGraph` в режиме LINEAGE.

### `/relay` — Студент: маркетплейс

Поиск/фильтры по всем обработанным проектам: домен, модальность, наличие датасета, «только чистый донор» (TRL 6-7).

### `/relay/project?tab=...` — Студент: карточка проекта

- **passport** — как в досье, плюс быстрые переходы в supply/demand.
- **supply** — карточки активов донора.
- **demand** — открытые задачи со статусами (OPEN/RESERVED_PENDING/ASSIGNED/COMPLETED); у OPEN — кнопка «Взять эстафету» → `ClaimModal` (ФИО студента и научрука, опционально новый заголовок, обязательный чекбокс citation-контракта).
- **synergy** — свободный поиск «Corporate Bounty Funnel», граф `SynergyGraph` в режиме SYNERGY, список матчей demand↔supply с % синергии и разбивкой формулы, генерация Synergy Merge Spec.
- **lineage** — тот же граф поколений.
- **package** — генерация/просмотр/копирование/скачивание `HANDOVER_PASSPORT.md` и `CITATION.cff`.

### `/dean?tab=...` — Деканат: аналитика

- **treemap** — узкие места (7 макрокатегорий → HDBSCAN-микрокластеры), клик открывает ROI-карточку и экспорт грант-обоснования.
- **golden** — bubble-чарт «золотого резерва» (ценность актива × горизонт продолжения), клик добавляет проект в банк тем.
- **trl** — список проектов TRL 6-7, готовых к передаче в индустрию/патентованию.
- **export** — чеклист до 30 тем «золотого резерва», экспорт банка тем на следующий учебный год (markdown).
- **moderation** — непризнанные внешние домены из репозиториев студентов, ожидающие апрува деканата.
- **finops** — расход LLM за день vs бюджет, % использования, стоимость на проект.
- Общая кнопка «Пересчитать кластеры» (принудительный ретрижер HDBSCAN).

## Запуск локально

### Вариант 1 — Docker Compose (рекомендуется, поднимает весь стек)

Требуется Docker + Docker Compose plugin.

```bash
git clone https://github.com/NoName1247/HackatonGoogle.git
cd HackatonGoogle
cp .env.example .env        # и отредактируйте SECRET_KEY/пароли/API-ключи под себя
docker compose up -d --build
```

Приложение будет на **http://localhost:8080** (nginx проксирует `/` на фронтенд, `/api/` на backend). Без `GEMINI_API_KEY`/`OPENAI_API_KEY` система работает на детерминированном fallback-экстракторе (без LLM).

> По умолчанию `docker-compose.yml` целится в `env_file: .env.example`. Если вы создали `.env`, поменяйте `env_file:` на `.env` во всех сервисах, либо просто редактируйте `.env.example` напрямую для локального теста.

Логи: `docker compose logs -f api worker-auditor`. Остановить: `docker compose down` (данные останутся в volumes; `-v` — удалить всё).

### Вариант 2 — backend и frontend по отдельности, без Docker

**Требования:** Python ≥3.12, Node ≥18 (в проде используется Node 20), запущенные PostgreSQL 16, Redis 7.2, Qdrant ≥1.12 (можно поднять их через `docker compose up -d postgres redis qdrant`, а API/воркеры/фронтенд — локально).

Системные пакеты для backend (Debian/Ubuntu): `build-essential libgl1 libglib2.0-0 libgomp1` (нужны onnxruntime/RapidOCR).

```bash
# 1. Postgres/Redis/Qdrant — быстрее всего через compose:
docker compose up -d postgres redis qdrant

# 2. Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install .
export DATABASE_URL=postgresql+asyncpg://horizon:horizon_secure_pwd@localhost:5432/horizon_relay
export REDIS_STATE_URL=redis://localhost:6379/0
export REDIS_CACHE_URL=redis://localhost:6379/1
export QDRANT_HOST=localhost
export BLOB_STORAGE_DIR=/tmp/horizon-blobs
mkdir -p /tmp/horizon-blobs/{pdf,md}

uvicorn main_api:app --host 0.0.0.0 --port 8000 --loop uvloop --http httptools
# схема БД и demo-данные создаются автоматически при первом старте

# в отдельных терминалах (нужны те же env-переменные выше):
celery -A workers.worker_parser  worker -Q q_parser   --pool=prefork --concurrency=1 --max-tasks-per-child=50 --loglevel=INFO
celery -A workers.worker_probe   worker -Q q_probe    --pool=threads --concurrency=4 --loglevel=INFO
celery -A workers.worker_auditor worker -Q q_auditor  --pool=threads --concurrency=4 --loglevel=INFO
celery -A workers.worker_synergy worker -Q q_synergy  --pool=threads --concurrency=2 --loglevel=INFO
celery -A workers.worker_cron    worker -Q q_cron     --pool=solo --beat --loglevel=INFO
```

```bash
# 3. Frontend (в отдельном терминале)
cd frontend
npm install
export NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
npm run dev
```

Фронтенд — **http://localhost:3000**, backend API — **http://localhost:8000/api/v1** (без всех 5 воркеров пайплайн загрузки диплома зависнет на соответствующем шаге, но каталог/аналитика на demo-данных будут работать после первого старта API).

Без ключей `GEMINI_API_KEY`/`OPENAI_API_KEY` аудит работает на встроенном детерминированном экстракторе.

## Переменные окружения (`.env.example`)

| Переменная | Назначение |
|---|---|
| `APP_ENV` | имя окружения |
| `SECRET_KEY` | зарезервирован, сейчас не используется ни одним auth-механизмом |
| `NEXT_PUBLIC_API_URL` | базовый URL API для фронтенда |
| `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` | креды Postgres-контейнера |
| `DATABASE_URL` | DSN SQLAlchemy async (`postgresql+asyncpg://...`) |
| `REDIS_STATE_URL` | Redis db=0 — очереди Celery, SSE-стримы, локи, rate-limit (без TTL) |
| `REDIS_CACHE_URL` | Redis db=1 — L2-кэш синергии/проб/feasibility-gate (всегда с TTL) |
| `QDRANT_HOST`/`QDRANT_HTTP_PORT`/`QDRANT_GRPC_PORT` | подключение к Qdrant |
| `BLOB_STORAGE_DIR` | локальное CAS-хранилище PDF и zstd-сжатых markdown |
| `GEMINI_API_KEY`/`OPENAI_API_KEY` | ключи LLM (LiteLLM cascade); если пусто — детерминированный fallback без LLM |
| `GITHUB_PAT_POOL` | список GitHub PAT через запятую, ротация в Redis |
| `AUTO_ALLOWLIST_DOMAINS` | домены, автоматически разрешённые в Artifact Probe |
| `DAILY_LLM_BUDGET_USD` | дневной лимит расходов на LLM |
| `MAX_PAGES_PROCESSED` | лимит страниц PDF |
| `MAX_MAP_CHUNKS_PER_THESIS` | лимит параллельных чанков на главы |
| `MAX_TOTAL_TOKENS_PER_JOB` | лимит токенов на job |
| `ONNX_MAX_CONCURRENT` | лимит параллельных ONNX-инференсов |

Продакшн-развёртывание — см. **[SERVER.md](SERVER.md)**.
