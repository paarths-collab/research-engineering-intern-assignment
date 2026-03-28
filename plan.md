# NarrativeSignal Live Data Migration Plan

## Goal
Move Polar, Network Graph, Perspective, Streamgraph, and Chatbot from static snapshots to a unified live data pipeline with hourly ingestion, incremental refresh, and full 24h recompute at 1000 in-window new posts.

## Scope
- Backend:
  - Unified ingestion and refresh orchestration
  - Shared live storage (DuckDB) and cache (Redis)
  - API updates for Polar, Network, Streamgraph, Perspective, Chatbot
- Frontend:
  - Live freshness indicators
  - Focused subreddit handling
  - Loading and stale-state behavior

## Folder Structure (Target)
- backend/
  - config/
    - live_pipeline_config.py
  - services/
    - unified_ingestion_service.py
    - metrics_refresh_service.py
    - scheduler.py
    - redis_cache.py
  - polarize_1/
  - networkgraph/
  - streamgraph2/
  - perspective/
  - hybrid_chatbot/
- frontend/
  - app/
    - polar/
    - intelligence/
    - stream/
    - perspective/
  - components/
    - polar/
    - network/
    - stream/

## Refresh Rules
1. Hourly incremental ingestion and metric updates.
2. Immediate full 24h recompute trigger when newly ingested in-window posts reach 1000 before next hourly run.
3. Keep only rolling 24h post window in live tables.

## Data Contract
- Common response metadata for all module APIs:
  - last_refreshed_at
  - post_count_24h
  - refresh_mode (incremental | full_24h)
  - focused_subreddits

## Implementation Phases
1. Foundation
   - Add config module and validate env at startup.
   - Add missing dependency checks (Reddit creds, DuckDB, Redis).
2. Ingestion
   - Build hourly async Reddit ingestion for focused subreddits.
   - Normalize and deduplicate post rows.
3. Metrics
   - Recompute echo/domain/similarity incrementally.
   - Trigger full 24h recompute at threshold.
4. API Integration
   - Switch module internals to live DuckDB + Redis cache-first reads.
   - Preserve current endpoint signatures where possible.
5. Frontend Integration
   - Add freshness badges and loading/stale states on all target pages.
6. Validation
   - Integration tests for each module.
   - End-to-end refresh test and dashboard verification.

## Delivery Checklist
- [ ] .gitignore updated before install/build actions.
- [ ] Backend virtualenv setup complete.
- [ ] Python dependencies installed.
- [ ] Node dependencies installed (root + frontend).
- [ ] plan.md added at repo root.
- [ ] Git initialized and remote configured.
- [ ] Initial commit pushed to GitHub.
