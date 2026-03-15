"""
Pipeline Orchestrator
Coordinates all 9 layers of the SimPPL intelligence engine.
Manages run state, timing, and output JSON generation.
"""
import asyncio
import json
import uuid
from datetime import date, datetime, timezone
from collections import Counter
from pathlib import Path
from typing import List, Optional

from app.config import get_settings
from app.database.models import (
    RawPost, GeoCandidate, ResolvedLocation, StructuredEvent,
    NewsBundle, NarrativeIntel, ImpactScore, EventCluster,
    MapEvent, PipelineStatus,
)
from app.pipeline.ingestion import fetch_reddit_posts, persist_raw_posts, get_existing_posts_for_today
from app.pipeline.geo_filter import fast_geo_filter
from app.pipeline.geo_resolver import resolve_all_candidates
from app.pipeline.event_structurer import structure_all_events
from app.pipeline.news_correlator import correlate_all_events
from app.pipeline.intelligence import analyse_all_events
from app.pipeline.impact_scorer import score_all_events
from app.pipeline.clustering import cluster_events
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_current_status: Optional[PipelineStatus] = None


def get_current_status() -> Optional[PipelineStatus]:
    return _current_status


async def run_pipeline(run_id: Optional[str] = None) -> PipelineStatus:
    global _current_status

    run_id = run_id or str(uuid.uuid4())[:8]
    status = PipelineStatus(
        run_id=run_id,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    _current_status = status

    try:
        # ── Layer 1: Ingestion ───────────────────────────────
        logger.info(f"[{run_id}] Layer 1 — Checking for existing data")
        posts: List[RawPost] = get_existing_posts_for_today()
        
        if posts:
            logger.info(f"[{run_id}] Reusing {len(posts)} posts from database")
        else:
            logger.info(f"[{run_id}] No existing data. Fetching from Reddit...")
            posts = await fetch_reddit_posts()
            persist_raw_posts(posts)
        
        status.posts_ingested = len(posts)

        if not posts:
            status.status = "complete"
            status.finished_at = datetime.now(timezone.utc).isoformat()
            logger.warning(f"[{run_id}] No posts ingested. Exiting.")
            return status

        posts_map: dict[str, RawPost] = {p.id: p for p in posts}

        # ── Layer 2: Fast Geo Filter ─────────────────────────
        logger.info(f"[{run_id}] Layer 2 — Fast Geo Filter")
        candidates: List[GeoCandidate] = fast_geo_filter(posts)
        status.geo_candidates = len(candidates)

        if not candidates:
            status.status = "complete"
            status.finished_at = datetime.now(timezone.utc).isoformat()
            logger.warning(f"[{run_id}] No geo candidates found.")
            return status

        # ── Layer 3: LLM Geo Resolution ──────────────────────
        logger.info(f"[{run_id}] Layer 3 — LLM Geo Resolution")
        resolved_pairs: List[tuple[GeoCandidate, ResolvedLocation]] = \
            await resolve_all_candidates(candidates)

        geo_map: dict[str, ResolvedLocation] = {
            loc.name: loc for _, loc in resolved_pairs
        }

        # ── Layer 4: Event Structuring ───────────────────────
        logger.info(f"[{run_id}] Layer 4 — Event Structuring")
        events: List[StructuredEvent] = await structure_all_events(resolved_pairs)
        status.events_structured = len(events)

        if not events:
            status.status = "complete"
            status.finished_at = datetime.now(timezone.utc).isoformat()
            return status

        # ── Layer 5: News Correlation ────────────────────────
        logger.info(f"[{run_id}] Layer 5 — News Correlation")
        bundles: List[NewsBundle] = await correlate_all_events(events)
        status.news_fetched = sum(b.news_count for b in bundles)
        bundles_map: dict[str, NewsBundle] = {b.event_id: b for b in bundles}

        # Drop low-confidence no-news events (unless high engagement)
        events = [
            e for e in events
            if bundles_map.get(e.id, NewsBundle(event_id=e.id)).news_count > 0
            or posts_map.get(e.post_id, RawPost(
                id="", title="", subreddit="", score=0,
                num_comments=0, created_utc=0
            )).engagement_score >= 500
        ]

        # ── Layer 6: Contextual Intelligence ────────────────
        logger.info(f"[{run_id}] Layer 6 — Intelligence Analysis")
        intel_list: List[NarrativeIntel] = await analyse_all_events(
            posts_map, events, bundles_map
        )
        intel_map: dict[str, NarrativeIntel] = {i.event_id: i for i in intel_list}

        # ── Layer 7: Impact Scoring ──────────────────────────
        logger.info(f"[{run_id}] Layer 7 — Impact Scoring")
        scores: List[ImpactScore] = score_all_events(
            events, posts_map, bundles_map, intel_map
        )
        scores_map: dict[str, ImpactScore] = {s.event_id: s for s in scores}

        # ── Layer 8: Clustering ──────────────────────────────
        logger.info(f"[{run_id}] Layer 8 — Event Clustering")
        clusters: List[EventCluster] = cluster_events(
            events, geo_map, posts_map, intel_map, scores_map, bundles_map
        )
        status.clusters_built = len(clusters)

        # ── Layer 9: Output JSON ─────────────────────────────
        logger.info(f"[{run_id}] Layer 9 — Generating Map JSON")
        map_events = _build_map_events(clusters, posts_map, bundles_map)
        _save_output(map_events, run_id)

        status.status = "complete"
        status.finished_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            f"[{run_id}] Pipeline complete - {len(map_events)} map events | "
            f"{status.posts_ingested} posts -> {status.clusters_built} clusters"
        )

    except Exception as e:
        logger.exception(f"[{run_id}] Pipeline FAILED: {e}")
        status.status = "failed"
        status.error = str(e)
        status.finished_at = datetime.now(timezone.utc).isoformat()

    return status


def _build_map_events(
    clusters: List[EventCluster],
    posts_map: dict[str, RawPost],
    bundles_map: dict[str, NewsBundle],
) -> List[MapEvent]:
    map_events = []
    for cluster in clusters:
        # Aggregate reddit metrics from cluster posts
        cluster_posts = [posts_map[pid] for pid in cluster.post_ids if pid in posts_map]
        sorted_posts = sorted(cluster_posts, key=lambda p: (p.score, p.num_comments), reverse=True)
        representative_title = sorted_posts[0].title if sorted_posts else f"{cluster.primary_location} is being discussed across Reddit."
        if representative_title and representative_title[-1] not in ".!?":
            representative_title = representative_title + "."

        subreddit_counts = Counter(p.subreddit for p in cluster_posts)
        primary_subreddit = subreddit_counts.most_common(1)[0][0] if subreddit_counts else ""
        latest_ts = max((p.created_utc for p in cluster_posts), default=0)
        latest_iso = datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat() if latest_ts else datetime.now(timezone.utc).isoformat()

        sentiment_to_score = {"negative": -0.6, "neutral": 0.0, "mixed": 0.15, "positive": 0.6}
        reddit_metrics = {
            "total_score": sum(p.score for p in cluster_posts),
            "total_comments": sum(p.num_comments for p in cluster_posts),
            "post_count": len(cluster_posts),
            "subreddits": list({p.subreddit for p in cluster_posts}),
        }

        # Aggregate news sources
        all_articles = []
        for pid in cluster.post_ids:
            # We need event_ids here — approximate via post_ids
            for bundle in bundles_map.values():
                for art in bundle.articles[:3]:
                    all_articles.append({
                        "title": art.title,
                        "url": art.url,
                        "source": art.source,
                        "trusted": art.is_trusted,
                    })

        # Deduplicate
        seen_urls = set()
        news_sources = []
        for art in all_articles:
            if art["url"] not in seen_urls:
                seen_urls.add(art["url"])
                news_sources.append(art)
            if len(news_sources) >= 5:
                break

        map_event = MapEvent(
            id=cluster.cluster_id,
            event_id=cluster.cluster_id,
            title=representative_title,
            locations=[ResolvedLocation(
                name=cluster.primary_location,
                lat=cluster.lat,
                lon=cluster.lon,
            )],
            timestamp=latest_iso,
            impact_score=cluster.average_impact,
            sentiment=cluster.dominant_sentiment,
            sentiment_score=sentiment_to_score.get((cluster.dominant_sentiment or "neutral").lower(), 0.0),
            risk_level=cluster.risk_level,
            subreddit=primary_subreddit,
            reddit_post_ids=[p.id for p in sorted_posts],
            reddit_metrics=reddit_metrics,
            news_sources=news_sources,
            confidence=cluster.confidence,
            summary=cluster.summary,
            strategic_implications=cluster.strategic_implications,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
        map_events.append(map_event)

    return map_events


def _save_output(map_events: List[MapEvent], run_id: str) -> str:
    Path(settings.DATA_DIR).mkdir(exist_ok=True)
    today = str(date.today())
    path = f"{settings.DATA_DIR}/global_events_{today}.json"

    payload = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "event_count": len(map_events),
        "events": [e.model_dump() for e in map_events],
    }

    with open(path, "w") as f:
        json.dump(payload, f, indent=2)

    logger.info(f"Output saved -> {path}")
    return path


def load_latest_output() -> Optional[dict]:
    """Load the most recent output JSON.

    Searches multiple candidate directories so the file is found regardless
    of whether uvicorn is launched from the project root or backend/globe/.
    """
    # Directory containing this very file: backend/globe/app/pipeline/
    _here = Path(__file__).resolve().parent
    search_dirs = [
        Path(settings.DATA_DIR),                    # configured (may be relative)
        _here.parent.parent.parent / "outputs",     # backend/globe/outputs/
        _here.parent.parent.parent.parent.parent / "outputs",  # project-root/outputs/
    ]
    for data_dir in search_dirs:
        try:
            files = sorted(data_dir.glob("global_events_*.json"), reverse=True)
            if files:
                with open(files[0]) as f:
                    return json.load(f)
        except Exception:
            continue
    return None
