from fastapi import APIRouter
from datetime import datetime, timezone
from app.config import get_settings
from app.database.connection import get_connection
from app.utils.geocoder import get_cache_size

router = APIRouter(prefix="/health", tags=["health"])
settings = get_settings()


@router.get("/")
async def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/detailed")
async def health_detailed():
    checks = {}

    # DB check
    try:
        conn = get_connection()
        conn.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # API keys configured
    checks["groq_configured"] = bool(settings.GROQ_API_KEY)
    checks["reddit_configured"] = bool(settings.REDDIT_CLIENT_ID)
    checks["newsapi_configured"] = bool(settings.NEWSAPI_KEY)
    checks["tavily_configured"] = bool(settings.TAVILY_API_KEY)
    checks["geo_cache_size"] = get_cache_size()

    overall = "ok" if checks["database"] == "ok" else "degraded"

    return {
        "status": overall,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
