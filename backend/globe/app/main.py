"""
SimPPL Globe — Geopolitical Intelligence Backend
FastAPI application entry point.
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database.connection import init_db, close_db
from app.api.routes import events, pipeline, health
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    Path(settings.DATA_DIR).mkdir(exist_ok=True)
    Path(settings.LOG_DIR).mkdir(exist_ok=True)
    init_db()
    logger.info("Database initialised")
    yield
    # Shutdown
    close_db()
    logger.info("Database connection closed")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Geo-First, News-Grounded, LLM-Assisted Geopolitical Event Engine. "
        "Ingests Reddit signals, validates via news correlation, "
        "and produces map-ready intelligence."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(health.router)
app.include_router(events.router)
app.include_router(pipeline.router)


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "endpoints": {
            "health": "/health",
            "events": "/events",
            "map_pins": "/events/map",
            "summary": "/events/summary",
            "run_pipeline": "POST /pipeline/run",
            "pipeline_status": "/pipeline/status",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
