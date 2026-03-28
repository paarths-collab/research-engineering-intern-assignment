"""
routers/intelligence.py — Aggregator for Modular Narrative Intelligence Routers
"""
from fastapi import APIRouter
from . import narratives, graph, subreddit, search, leaderboard

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

router.include_router(narratives.router)
router.include_router(graph.router)
router.include_router(subreddit.router)
router.include_router(search.router)
router.include_router(leaderboard.router)
