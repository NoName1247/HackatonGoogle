# Продакшн-развёртывание на Linux-сервере

Инструкция разворачивает полный стек Horizon Relay (`nginx` + `frontend` + `api` + 5 Celery-воркеров + `postgres` + `redis` + `qdrant`) через `docker-compose.yml` в корне репозитория.

## 1. Требования к серверу

- Linux x86_64 с systemd (Ubuntu 22.04/24.04 LTS или Debian 12 — ниже команды для них).
- Минимум по суммарным лимитам из `docker-compose.yml` (`mem_limit`): ~4.5 ГБ RAM, 4+ vCPU с запасом. Рекомендуется **8 ГБ RAM / 4 vCPU / 40 ГБ диска** — первая загрузка ONNX-моделей (fastembed/bge-m3/reranker) и рост `postgres_data`/`qdrant_data` требуют места.
- Открытый исходящий интернет (egress) — нужен для вызовов LLM API, GitHub/HuggingFace/Zenodo и загрузки ONNX-моделей при первом запуске.
- Домен (опционально, но нужен для TLS) с A-записью на IP сервера.

## 2. Подготовка сервера

```bash
sudo apt-get update && sudo apt-get upgrade -y

# Базовый firewall
sudo apt-get install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Непривилегированный пользователь для деплоя (если ещё не создан)
sudo adduser --disabled-password --gecos "" horizon
sudo usermod -aG sudo horizon
su - horizon
```

### Docker Engine + Compose plugin

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker   # или перелогиньтесь

docker --version
docker compose version
```

## 3. Получение кода

```bash
sudo mkdir -p /opt/horizon-relay
sudo chown "$USER":"$USER" /opt/horizon-relay
git clone https://github.com/NoName1247/HackatonGoogle.git /opt/horizon-relay
cd /opt/horizon-relay
```

## 4. Конфигурация окружения

```bash
cp .env.example .env
nano .env   # или vim/vi
```

Обязательно поменять перед продом:

| Переменная | Что сделать |
|---|---|
| `SECRET_KEY` | заменить на случайную строку: `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | заменить на сильный пароль |
| `DATABASE_URL` | обновить пароль в строке подключения в соответствии с `POSTGRES_PASSWORD` |
| `NEXT_PUBLIC_API_URL` | `http://<ваш-домен>/api/v1` (или `https://...`, если TLS настроен на этом же nginx/перед ним) |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | ключ хотя бы одного провайдера — иначе аудит работает без LLM (детерминированный fallback, более грубая оценка) |
| `GITHUB_PAT_POOL` | один-несколько GitHub PAT через запятую — иначе Artifact Probe быстро упирается в анонимный rate-limit GitHub API |
| `DAILY_LLM_BUDGET_USD` | реальный дневной бюджет на LLM (жёсткий cutoff в коде) |

**Важно:** `docker-compose.yml` по умолчанию читает `env_file: .env.example` для сервисов `api`/`worker-*`. После того как вы создали настоящий `.env`, либо:
- замените во всех 6 блоков (`api`, `worker-parser`, `worker-probe`, `worker-auditor`, `worker-synergy`, `worker-cron`) строку `env_file: .env.example` на `env_file: .env`, **либо**
- отредактируйте значения прямо в `.env.example` (проще, но хуже с точки зрения git-гигиены — не коммитьте секреты).

Правьте `docker-compose.yml` вручную в редакторе (шесть мест `env_file: - .env.example` → `- .env`) — надёжнее, чем однострочный `sed` по многострочному YAML.

## 5. Первый запуск

```bash
cd /opt/horizon-relay
docker compose up -d --build
```

Первая сборка качает/собирает образ `horizon-relay-backend` (используется и API, и всеми 5 воркерами) и `horizon-relay-frontend` — может занять несколько минут. При первом старте `api`:
- создаёт схему Postgres и коллекции Qdrant автоматически (без Alembic, идемпотентно);
- если таблица `projects` пуста — засевает ~200 демо-проектов (`backend/scripts/seed_demo_data.py`);
- фоновые воркеры при первом использовании синергии скачивают ONNX-модели эмбеддингов (нужен интернет, занимает место в `/var/cache/fastembed` внутри контейнера `worker-synergy`).

Проверка состояния:

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker-auditor worker-synergy
```

Все сервисы со `healthcheck` (postgres, redis) должны быть `healthy`; остальные — `running`.

Приложение доступно на `http://<ip-или-домен>:8080` — так как `nginx` в compose мапит `8080:80` на хосте.

## 6. TLS / публичный домен на 80/443

Внутренний `nginx` в compose слушает `:80` внутри контейнера и опубликован на хостовый `8080`. Для production с HTTPS проще поставить перед ним ещё один nginx (или Caddy) на хосте, слушающий 80/443 и проксирующий на `127.0.0.1:8080`, с TLS через Let's Encrypt.

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

`/etc/nginx/sites-available/horizon-relay`:

```nginx
server {
    listen 80;
    server_name your-domain.example;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location ~ ^/api/v1/jobs/.+/stream$ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        add_header X-Accel-Buffering "no" always;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/horizon-relay /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.example
```

После выпуска сертификата обновите `.env`: `NEXT_PUBLIC_API_URL=https://your-domain.example/api/v1`, затем:

```bash
docker compose up -d --build frontend
```

(`NEXT_PUBLIC_API_URL` запекается в билд Next.js, поэтому смена значения требует пересборки образа `frontend`, а не просто перезапуска контейнера.)

## 7. Автозапуск при перезагрузке сервера

Все сервисы в `docker-compose.yml` имеют `restart: unless-stopped` — после `docker compose up -d` они переживут перезапуск Docker daemon. Для полного автозапуска после ребута сервера достаточно, что Docker сам стартует как systemd-сервис:

```bash
sudo systemctl enable docker
```

Контейнеры с `unless-stopped` поднимутся автоматически вместе с docker daemon.

## 8. Обновление версии (деплой нового коммита)

```bash
cd /opt/horizon-relay
git pull origin main
docker compose up -d --build
```

Пересобираются только изменившиеся образы (`api`/`worker-*` используют общий образ `horizon-relay-backend`, пересобирается один раз). Миграций схемы нет — `create_all` идемпотентен, но учтите: при изменении колонок существующих таблиц потребуется ручной `ALTER TABLE` (в проекте нет Alembic).

Откат:

```bash
git checkout <предыдущий-коммит-или-тег>
docker compose up -d --build
```

## 9. Бэкапы

Персистентные данные лежат в named volumes: `postgres_data`, `qdrant_data`, `redis_data`, `horizon_blobs`.

```bash
# Postgres — логический дамп
docker compose exec -T postgres pg_dump -U horizon horizon_relay | gzip > backup_$(date +%F).sql.gz

# Qdrant — снапшот коллекций через его HTTP API (на хосте, если порт проброшен, либо docker exec curl изнутри сети)
docker compose exec api sh -c "curl -s -X POST http://qdrant:6333/collections/<name>/snapshots"

# Blob storage (оригиналы PDF + markdown-слепки)
docker run --rm -v horizon-relay_horizon_blobs:/data -v "$PWD":/backup alpine \
    tar czf /backup/blobs_$(date +%F).tar.gz -C /data .
```

Разумный минимум — ежедневный `pg_dump` в cron + ротация бэкапов через `find ... -mtime +14 -delete`.

## 10. Логи и мониторинг

```bash
docker compose logs -f --tail=200 api
docker compose logs -f --tail=200 worker-parser worker-probe worker-auditor worker-synergy worker-cron
docker compose logs -f nginx

# Ресурсы по контейнерам (сверка с заданными mem_limit/cpus)
docker stats
```

Признаки проблем, на которые стоит смотреть:
- застрявшие задачи в `q_parser`/`q_auditor`/`q_synergy` — долгие OCR-страницы или LLM-таймауты (см. `MAX_PAGES_PROCESSED`, `MAX_TOTAL_TOKENS_PER_JOB` в `.env`);
- `FailedJobDLQ` в Postgres — пайплайн ушёл в карантин по конкретному проекту;
- `DomainModerationQueue` — внешние домены репозиториев, ожидающие апрува деканата (видно на `/dean?tab=moderation`);
- расход LLM у `DAILY_LLM_BUDGET_USD` — виден на `/dean?tab=finops`, хард-лимит зашит в `core/auditor_and_scorer.py`.

## 11. Остановка / полная очистка

```bash
docker compose down            # остановить, volumes и образы остаются
docker compose down -v         # + удалить volumes (БД, векторный индекс, blob-хранилище — НЕОБРАТИМО)
```

## 12. Известные ограничения прод-готовности (на момент этой инструкции)

- В API нет аутентификации/авторизации ни на одном роуте, CORS открыт на `*` — перед реальным публичным продом нужно либо закрыть `/api/v1/*` на уровне внешнего nginx (allowlist IP / basic-auth / VPN), либо добавить auth-слой в `main_api.py`.
- Секреты (`SECRET_KEY`, `POSTGRES_PASSWORD`, LLM-ключи) лежат в `.env` в открытом виде на диске сервера — для серьёзного прода стоит завести секрет-менеджер (Vault, SOPS, Docker secrets) вместо `env_file`.
- Нет готового TLS/reverse-proxy внутри самого compose-стека — раздел 6 выше закрывает это внешним nginx+certbot.
