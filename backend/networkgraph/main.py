from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from networkgraph.data.loader import load_all, get_store
from networkgraph.routers import graph, transport, narrative, user, analyze

import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# ── Load data at import time (before any request) ─────────────────────────────
load_all()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sntis.main")


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("SNTIS Backend ready. %s", get_store().row_counts())
    yield
    log.info("SNTIS Backend shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SNTIS — Semantic Narrative Transport Intelligence System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(graph.router)
app.include_router(transport.router)
app.include_router(narrative.router)
app.include_router(user.router)
app.include_router(analyze.router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
def health():
    store = get_store()
    return {
        "status": "ok" if store.ready else "loading",
        "datasets_loaded": store.row_counts(),
        "version": "1.0.0",
    }

@app.get("/", include_in_schema=False)
def root():
    return {"message": "SNTIS Backend API", "docs": "/docs", "health": "/health"}