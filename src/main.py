"""FastAPI entry point. Run from the project root: uvicorn main:app --reload --app-dir src

Routes are served at the root (local dev: the Vite proxy strips /api) and under /api (one-container
deploy: the built React app in frontend/dist is served at / and calls /api/...)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from persistence.db import connect, init_db
from rag.config import ROOT

FRONTEND_DIST = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect()
    try:
        init_db(conn)
    finally:
        conn.close()
    yield


app = FastAPI(
    title="Plant Operation Manager API",
    description="Routes floor supervisors' questions to safety, maintenance or quality documentation.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8501", "http://localhost:7860"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(router, prefix="/api", include_in_schema=False)

# Serve the built UI when it exists (Docker image, or after `npm run build`). Mounted last, so
# API routes and /docs win; html=True serves index.html at /.
if (FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="ui")
