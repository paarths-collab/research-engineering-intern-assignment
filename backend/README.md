# NarrativeSignal Backend

A single FastAPI app (`main.py`) that mounts several sub-apps under one origin. Setup, run commands, environment variable names, and the `/health` semantics are in the root README under "Running the Backend". This file covers the parts that matter for the backend itself.

## Mounts

| Prefix | Package | What it serves |
|---|---|---|
| `/api/polar` (also `/api`) | `polarize_1/` | Media ecosystem and domain views |
| `/api/network` | `networkgraph/` | Subreddit, domain, and author graph (modes: `spread`, `sources`, `amplifiers`, `all`) |
| `/api/stream` | `streamgraph2/` | Daily volume series with z-score spikes, clusters, and an on-demand spike pipeline |
| `/api/globe` | `globe/` | Event clusters and map data, plus an on-demand collection pipeline |
| `/api/chatbot` | `hybrid_chatbot/` | Dataset-grounded chat |
| `/api/perspective` | `perspective/` | Persona roleplay simulation |

Each sub-app that fails to import is replaced with an empty `FastAPI()` and recorded in `MODULE_LOAD_ERRORS`. Its routes then return 404. `GET /health` reports these failures.

## Chatbot (`hybrid_chatbot/`)

`POST /api/chatbot/query` takes `{"query", "debug", "web_search"}`. For each request:

1. **Dataset retrieval** (`dataset_context.py`). Lexical token overlap over text snippets generated from rows of 7 CSVs: `narrative_registry`, `narrative_intelligence_summary`, `subreddit_intelligence_summary`, `echo_chamber_scores`, `author_influence_profile`, `daily_volume_v2`, and `subreddit_domain_flow_v2`. The top 8 snippets are kept. There is no embedding model.
2. **SQL** (`sql_engine.py`). `SQLTranslator` matches the question against fixed keyword templates. User-derived values (subreddit, narrative, date window) are bound as parameters, and the SQL text is constant. The templates run on a DuckDB file built from the 12 CSVs in `config.CSV_TABLES`.
3. **Answer selection** (`pipeline.py`). In order:
   - Deterministic answer for some ranking questions.
   - A coverage or unavailability message when the SQL cannot answer.
   - An out-of-dataset message when neither the dataset nor the SQL is relevant and web search is off.
   - Optional web search (`web_search.py`: DuckDuckGo HTML results plus article text extraction).
   - One LLM call (`llm_client.py`, OpenAI-compatible, Groq by default). If it fails, a labelled `fallback_template` answer is returned.

The DuckDB file is built by `build_db.py` or lazily by the API. Its date range is derived from the dated tables. It currently spans 2024-07-23 to 2025-02-18.

The planner rejects recognized scopes that its template cannot apply (including dates on snapshot aggregates, narrative-scoped generic counts, and multiple subreddit names). These return `insufficient_coverage` with the reason and requested date window, without running a broader query or calling the LLM. Bare subreddit names match whole names deterministically. SQL validation and execution use a cursor per request. Dated series are preserved in full in API evidence and synthesis prompts; template fallbacks also summarize the complete interval and peak.

### Response provenance

Non-debug responses include:

- `answer`, `answer_mode`: one of `deterministic_sql`, `deterministic_dataset`, `llm_synthesis`, `fallback_template`, `out_of_dataset`, `sql_unavailable`, `insufficient_coverage`.
- `llm_used`: true only for `llm_synthesis`.
- `dataset`: `name`, `description`, `snapshot` (always `"historical"`), `date_range` (`start`, `end`), `tables_used`.
- `evidence[]`, each with a `type`:
  - `sql`: `tables`, `description`, `query`, `rows`, `row_count`.
  - `dataset_snippet`: `table`, `row_key`, `row_index`, `date`, `text`, `score`.
  - `web`: `url`, `title`, `source`.
- `sql`: `status` is one of `ok`, `not_applicable` (no template matched), `unavailable` (a required table or the database is missing), `insufficient_coverage` (no data for the window, entity, or values), or `error`. Also `description`, `query`, `rows`, `error`, `reason`, `coverage` (`status` is `full`, `partial`, `none`, or `not_applicable`), `params`, `tables`, `missing_tables`, `date_window`.
- `retrieval`: `method` (`lexical_token_overlap`), `sql` (`keyword_template`), `embeddings` (`false`), `dataset_top_k`, `web` (`duckduckgo_html` or `disabled`).

With `debug: true`, the response also includes `debug` (`llm_model`, `llm_base_url`, `web_search_enabled`) and keeps `route`, `timing`, `dataset_chunks`, and `web_articles`. Without debug, those four keys are removed.

### Not on the mounted path

These files are not imported by `main.py` or by the chatbot pipeline. They are legacy experiments:

- `hybrid_chatbot/vector_store.py` and `hybrid_chatbot/build_index.py` (embedding index)
- `hybrid_chatbot/router.py` and `hybrid_chatbot/prompting.py`
- `hybrid/` and `hybrid_crew/` (multi-agent research pipeline)

## Globe (`globe/`)

- **Collection** (`app/pipeline/`). `ingestion.py` pulls recent posts from the subreddits in `REDDIT_SUBREDDITS` through asyncpraw. `news_correlator.py` searches Tavily, then NewsAPI, GNews, and NewsData. Geocoding and event analysis use Groq. `clustering` groups posts into events, and `orchestrator.py` runs the whole pipeline.
- **Trigger.** Nothing schedules the pipeline. It runs only when `POST /api/globe/pipeline/run` (background) or `POST /api/globe/pipeline/run/sync` is called. `GET /api/globe/pipeline/status` reports the last run.
- **Read routes.** `GET /api/globe/events/`, `/events/summary`, `/events/map`, `/events/{event_id}`. `GET /api/globe/health/` and `/health/detailed`.
- **Analysis routes.** `POST /api/globe/events/news`, `/events/headline-analysis`, `/events/{event_id}/analyze`, `/events/ai-analysis`, `/events/{event_id}/news-analysis`, and `/events/{event_id}/ai-analysis`.
- **News per cluster.** Each cluster's `news_sources` comes only from that cluster's own events, up to 5 articles.

## Perspective (`perspective/`)

Routes: `GET /api/perspective/personas`, `GET /api/perspective/news-presets?limit=`, and `POST /api/perspective/simulate`. The simulate body takes `nodes`, `edges`, `debate_rounds` (1 to 20, default 3), and `options`.

The simulator is an illustrative persona roleplay sandbox. Its output is labelled:

- Top level: `simulated: true`, `simulation_notice` (states that the output is simulated and is not observed community data or a validated forecast), and `generation` (`reactions` counts for `llm` and `fallback_template`, `rounds: "template"`, `model`).
- Each reaction: `generation` (`llm` or `fallback_template`), `simulated`, `model` (LLM only), and `fallback_reason` (`missing_key`, `empty`, or `error`, fallback only).
- Each round and turn: `generation: "template"` and `simulated: true`. Rounds never call an LLM.

Reactions come from one sequential Groq call per persona, using `PERSPECTIVE_GROQ_MODEL`. The call is made only when `GROQ_API_KEY` is set. Before simulating, the service calls the Globe API at `PERSPECTIVE_GLOBE_API_URL` for news context. If that call fails, the simulation continues without it.

Globe input provenance (`is_mock`, `data_source`, `data_notice`, `data_generated_at`) survives preset generation, analysis caches, and frontend caches. Input source labels are separate from the reaction's `simulated` label. Unrelated events are not added as supporting context. Connector outputs carry `generated_output` and `connectorIds`; the board retains all branches and reconciles a one-to-one result to its requested connector. Derived connectors are excluded from subsequent simulation inputs.

## Other mounted apps

`polarize_1/`, `networkgraph/`, and `streamgraph2/` expose the routes in their own modules. `streamgraph2` uses `DATABASE_URL` when available, otherwise a local DuckDB (`STREAMGRAPH2_DUCKDB_PATH`). Fallback startup transactionally seeds empty echo-score, domain-flow and distinctive-domain tables from bundled CSVs in `DATA_PATH` (default project `data/`). Nonempty persisted tables are preserved on restart. Timeline helpers also read CSV data.

## Deployment files

- `backend/Dockerfile`: `python:3.12-slim`. Copies `data/` to `/app/seed_data`. Its HEALTHCHECK calls `/health`.
- `backend/entrypoint.sh`: copies missing seed files into `$DATA_PATH` on every boot, preserving existing files unless `SEED_FORCE=1`; runs `patch_db.py`, then starts uvicorn.
- `render.yaml`: Docker web service with a disk at `/app/data` and `healthCheckPath: /health`.
- `vercel.json` and `frontend/vercel.json`: frontend-only Vercel builds. Next.js rewrites `/api/*` to the Render origin from server-side `BACKEND_API_URL` or `frontend/deployment.json`; the legacy `api/index.py` is not deployed.
- `docker-compose.yml`: local backend container on port 8000.

## Tests

- `hybrid_chatbot/tests/`: API, pipeline, coverage, and SQL bootstrap tests.
- `tests/test_service_health.py`: the `/health` payload helper.
- `perspective/tests/test_simulate_labels.py`: labelling and fallback behaviour, with the provider call stubbed.
- `globe/tests/` (run from `backend/globe`, see `pytest.ini`): builds a test app from the actual routers, with provider calls stubbed.
- `tests/test_streamgraph_bootstrap.py`: fresh fallback startup and preservation of persisted ecosystem metrics.
- `frontend/tests/` (`cd frontend && npm test`): board branch retention, connector handles, and provenance through map normalization and preset caching.

Run commands are in the root README.

## User accounts, operator access and work admission

`user_auth.py` uses FastAPI Users with Argon2 passwords and revocable, hashed opaque sessions. Accounts live in the private `narrative_auth` PostgreSQL schema on `DATABASE_URL`, with optional `AUTH_DATABASE_URL` override. Auth tables are created on startup without changing analytical tables. Exposed account routes are `/api/auth/register`, `/login` (URL-encoded `username` and `password`), `/logout`, `/me`, and `/status`. There is no public role-setting or account-administration API. Responses omit password hashes and tokens, redact rejected inputs, and use `Cache-Control: no-store`. Sessions expire after 24 hours and are revoked on logout.

`api_security.py` wraps the unified API and standalone chatbot. Signed-in users can POST only the explicit analysis allowlist: chatbot queries, Perspective simulations, Polar briefs, Network analysis, Stream media/topic/event analysis, and Globe event/news analysis. Globe collection, Stream spike collection, `/diag`, and unknown writes require `Authorization: Bearer <NARRATIVE_API_TOKEN>` (at least 32 characters). No account flag grants operator access. Standalone chatbot deployments retain bearer-only access; the unified service supplies user-session authorization. GET/HEAD dashboards remain public. Cookie writes, including signup/login/logout, require `X-Narrative-CSRF: 1` and a trusted Origin when supplied. CORS applies `FRONTEND_ORIGINS` without enabling cross-origin credentialed access.

Production accounts require PostgreSQL and never use the analytical DuckDB fallback or an ephemeral SQLite database. Local account testing may explicitly set `AUTH_DATABASE_URL=sqlite+aiosqlite:///./accounts.sqlite` and `AUTH_COOKIE_SECURE=false`; Render always enforces Secure cookies and rejects SQLite. Missing or unreachable storage returns generic 503 errors for accounts. Email verification and recovery email delivery are not configured.

Defaults: `RATE_LIMIT_MAX=60` per client/module, `WORK_LIMIT_MAX=10` across authenticated work requests and client addresses, `RATE_LIMIT_WINDOW_SECONDS=60`, and 2 active work requests. Polar aliases share one bucket. State expires and client buckets are capped. Forwarded IP headers are not used by this middleware. Configure your trusted proxy separately; counters, locks and slots require one worker/instance. Shared persistent admission and a queue are required before horizontal or serverless scaling.

Members have an additional 3 requests per minute and `USER_DAILY_ANALYSIS_LIMIT=20` per UTC day. The daily reservation uses an atomic database upsert, survives restart, and remains capped under concurrent requests. Signup/login are limited before Argon2 work: one active auth operation, 30 per minute globally, and 10 per client/account in 5 minutes. Login rejects repeated form fields and unsupported encodings so the attempt limiter checks the actual login account. Auth bodies are limited to 16 KiB.

Work requests are capped at 256 KiB of actual received JSON, 8,000 characters per string, 512 array items, 128 object keys, and 12 levels of nesting. A shared, locked context budget permits 32 downstream attempts and stops starting new attempts after 180 seconds. Sync threads and async child tasks share it; provider retries and fallbacks consume it too. LLM SDK automatic retries are disabled and LLM outputs/timeouts are bounded. Reddit SDK HTTP attempts and automatic HTTP redirects also reserve a unit before each attempt. Background tasks retain the active slot through completion; budget failure marks collection jobs failed rather than publishing a complete result. HTTP spike jobs use deterministic supervision so CrewAI's internal calls cannot bypass the budget. These controls do not apply to independently launched CLI jobs.

Perspective validates graph expansion before any context/provider lookup: 64 nodes, 128 edges, unique identifiers, 8 personas, 4 headlines, 12 reactions, and 120 turns. News preset requests allow 1–30 entries. The frontend sends original inputs on repeated runs, excluding generated text. Globe collection scans at most 8 subreddits × 30 posts, reuses at most 240 stored posts, resolves at most 12 candidates, and correlates at most 8 structured events. Existing caches and persisted datasets remain available to public reads.

The public frontend offers sign-in and signup; user analysis uses its HttpOnly cookie through the same-origin proxy. The unlinked, noindex `/admin` page holds a manually supplied operator token only in tab memory. Account endpoints never receive that bearer. Sign out also clears the in-memory operator token. Analysis failures show server errors; rejected writes are never automatically retried against alternate origins. Tokens never belong in public environment variables, browser storage, query parameters, or logs. Use HTTPS for nonlocal traffic.

`tests/test_api_security.py` covers mount/alias protection, global work admission, chunked body limits, background concurrency, quota expiry, and atomic provider budgets. Perspective and frontend regressions cover graph expansion and credential forwarding.

`tests/test_user_auth.py` and `tests/test_user_analysis_access.py` cover real signup/login/logout, hashed sessions, expiry, inactive accounts, privilege rejection, persistent atomic quotas, CSRF, form ambiguity, credential redaction, and member/admin route separation.

The existing free native Render service can keep its Python runtime and start command. Set `WEB_CONCURRENCY=1`, `DATA_PATH=./data`, `STREAMGRAPH2_DUCKDB_PATH=./data/streamgraph2.duckdb`, `LOG_DIR=./logs`, and `NARRATIVE_BOOTSTRAP_NETWORK_DB=1`. This flag runs the network database CSV bootstrap in the unified lifespan and verifies all required tables before startup succeeds. Native free storage is ephemeral; the optional paid Docker Blueprint supplies persistence. Keep existing provider secrets when updating deployment environment variables.
