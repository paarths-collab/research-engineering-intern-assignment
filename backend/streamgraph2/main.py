"""
main.py — Unified Catalyst Intelligence Platform API

Organized into modular routers for Ecosystem and Spike analysis.
"""
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from streamgraph2.data import db
from streamgraph2.routers import ecosystem, spike

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("catalyst.main")


# ── Lifespan: load DB once at startup ───────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    retries = 5
    log.info("=" * 60)
    log.info("Catalyst Backend starting up...")
    
    for attempt in range(1, retries + 1):
        try:
            await db.init_pool()
            log.info("✓ Unified Catalyst Intelligence Platform ready")
            break
        except Exception as e:
            if attempt < retries:
                log.warning(f"  [DB] Startup connection failed (attempt {attempt}/{retries}): {e}. Retrying in 2s...")
                await asyncio.sleep(2)
            else:
                log.error(f"  [DB] FATAL: Could not connect to Neon DB after {retries} attempts.")
                raise
    
    yield
    log.info("Catalyst Backend shutting down.")
    await db.close_pool()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Catalyst Intelligence Platform",
    description="Media ecosystem analysis + spike attribution engine",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ecosystem.router, prefix="/api")
app.include_router(spike.router, prefix="/api")


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"], summary="Health check")
async def health():
    return {
        "status": "ok",
        "service": "catalyst-intelligence-platform",
        "modules": ["media_ecosystem", "spike_attribution"],
    }


@app.get("/", tags=["system"], include_in_schema=False)
def root():
    return {
        "message": "Catalyst Intelligence Platform API",
        "docs": "/docs",
        "health": "/health",
    }
