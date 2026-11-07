"""FastAPI entry point. Run from the project root: uvicorn main:app --reload --app-dir src"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from persistence.db import connect, init_db


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
