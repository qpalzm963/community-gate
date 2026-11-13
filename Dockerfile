# ---- Stage 1: Build Vue 3 frontend ----
FROM node:22-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python 3.12 FastAPI runtime ----
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GATE_HOST=0.0.0.0 \
    GATE_DATA_DIR=/app/data

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY --from=frontend-builder /build/backend/app/static ./backend/app/static

RUN pip install --no-cache-dir . && mkdir -p /app/data/snapshots

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
