FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/var/cache/fastembed

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/lib/horizon/blobs/pdf /var/lib/horizon/blobs/md /var/cache/fastembed

COPY . /app/
RUN mkdir -p /app/core /app/workers /app/scripts && \
    touch /app/core/__init__.py /app/workers/__init__.py /app/scripts/__init__.py && \
    pip install --root-user-action=ignore --upgrade pip && \
    pip install --root-user-action=ignore .

EXPOSE 8000

CMD ["uvicorn", "main_api:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop", "--http", "httptools"]
