from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date

from app.pipeline.orchestrator import load_latest_output
from app.database.connection import get_connection
from app.utils.logger import get_logger

router = APIRouter(prefix="/events", tags=["events"])
logger = get_logger(__name__)


@router.get("/")
async def get_events(
    risk_level: Optional[str] = Query(None, description="Filter by risk: Low|Medium|High"),
    confidence: Optional[str] = Query(None, description="Filter by confidence: Low|Medium|High"),
    min_impact: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
):
    """Return the latest processed map events."""
    data = load_latest_output()
    if not data:
        raise HTTPException(status_code=404, detail="No events data available. Run the pipeline first.")

    events = data.get("events", [])

    if risk_level:
        events = [e for e in events if e.get("risk_level") == risk_level]
    if confidence:
        events = [e for e in events if e.get("confidence") == confidence]
    if min_impact > 0:
        events = [e for e in events if e.get("impact_score", 0) >= min_impact]

    events.sort(key=lambda e: e.get("impact_score", 0), reverse=True)
    events = events[:limit]

    return {
        "generated_at": data.get("generated_at"),
        "total": len(events),
        "events": events,
    }


@router.get("/summary")
async def get_summary():
    """High-level summary of current global event landscape."""
    data = load_latest_output()
    if not data:
        raise HTTPException(status_code=404, detail="No events data available.")

    events = data.get("events", [])
    risk_dist = {"Low": 0, "Medium": 0, "High": 0}
    sentiment_dist = {}
    for e in events:
        r = e.get("risk_level", "Low")
        risk_dist[r] = risk_dist.get(r, 0) + 1
        s = e.get("sentiment", "neutral")
        sentiment_dist[s] = sentiment_dist.get(s, 0) + 1

    high_impact = [e for e in events if e.get("impact_score", 0) >= 0.5]

    return {
        "run_id": data.get("run_id"),
        "generated_at": data.get("generated_at"),
        "total_events": len(events),
        "risk_distribution": risk_dist,
        "sentiment_distribution": sentiment_dist,
        "high_impact_count": len(high_impact),
        "avg_impact": round(
            sum(e.get("impact_score", 0) for e in events) / len(events), 3
        ) if events else 0,
    }


@router.get("/map")
async def get_map_data():
    """Optimised payload for frontend globe rendering."""
    data = load_latest_output()
    if not data:
        raise HTTPException(status_code=404, detail="No events data available.")

    map_pins = []
    for e in data.get("events", []):
        for loc in e.get("locations", []):
            map_pins.append({
                "id": e["id"],
                "lat": loc.get("lat"),
                "lon": loc.get("lon"),
                "name": loc.get("name"),
                "title": e.get("title"),
                "impact_score": e.get("impact_score"),
                "risk_level": e.get("risk_level"),
                "sentiment": e.get("sentiment"),
                "confidence": e.get("confidence"),
                "summary": e.get("strategic_implications", [])[:1],
            })

    return {
        "generated_at": data.get("generated_at"),
        "pin_count": len(map_pins),
        "pins": map_pins,
    }


@router.get("/{event_id}")
async def get_event_detail(event_id: str):
    """Full detail for a single event cluster."""
    data = load_latest_output()
    if not data:
        raise HTTPException(status_code=404, detail="No events data available.")

    for event in data.get("events", []):
        if event.get("id") == event_id:
            return event

    raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found.")
