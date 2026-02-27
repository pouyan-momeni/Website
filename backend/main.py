"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.auth import router as auth_router
from backend.api.models import router as models_router
from backend.api.runs import router as runs_router, ws_router
from backend.api.queue import router as queue_router
from backend.api.schedules import router as schedules_router
from backend.api.monitoring import router as monitoring_router
from backend.api.users import router as users_router
from backend.api.marimo import router as marimo_router
from backend.api.notebooks import router as notebooks_router, ws_notebook_router
from backend.api.audit import router as audit_router
from backend.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("ALMPlatform starting in %s mode", settings.APP_MODE)
    logger.info("Database: %s", settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "configured")
    yield
    logger.info("ALMPlatform shutting down")


app = FastAPI(
    title="ALMPlatform",
    description="Financial Model Execution Platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.is_develop else None,
    redoc_url="/api/redoc" if settings.is_develop else None,
)

# CORS — allow frontend dev server in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"] if settings.is_develop else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(models_router)
app.include_router(runs_router)
app.include_router(ws_router)
app.include_router(queue_router)
app.include_router(schedules_router)
app.include_router(monitoring_router)
app.include_router(users_router)
app.include_router(marimo_router)
app.include_router(notebooks_router)
app.include_router(ws_notebook_router)
app.include_router(audit_router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "mode": settings.APP_MODE,
    }


@app.get("/api/config/mode")
async def get_mode():
    """Return the current application mode (public endpoint for frontend)."""
    return {"mode": settings.APP_MODE}
