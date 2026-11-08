# One container: React UI (built in stage 1) + FastAPI/LangGraph backend. Fly's remote builder
# builds this file; see docs/runbooks/deploy-fly.md.

# ---- stage 1: build the React app
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- stage 2: Python runtime
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALLOW_INGEST=0 \
    DEMO_TICKETS=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY tools/ tools/
# Pre-built Chroma index (read at runtime; rebuild locally with tools/scripts/ingest_docs.py)
COPY data/chroma/ data/chroma/
COPY --from=web /web/dist frontend/dist

# SQLite lives on the Fly volume: DATABASE_URL=sqlite:////data/app.db (set as a Fly secret)
EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
