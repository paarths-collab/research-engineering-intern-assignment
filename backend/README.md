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

## Other mounted apps

`polarize_1/`, `networkgraph/`, and `streamgraph2/` are mounted as they are. Their routes are listed in their own modules. `streamgraph2` reads `DATABASE_URL` when it is set and falls back to CSVs when it is not.

## Deployment files

- `backend/Dockerfile`: `python:3.12-slim`. Copies `data/` to `/app/seed_data`. Its HEALTHCHECK calls `/health`.
- `backend/entrypoint.sh`: copies the seed data into `$DATA_PATH` when `analysis_v2.db` is missing, runs `patch_db.py`, and starts uvicorn.
- `render.yaml`: Docker web service with a disk at `/app/data` and `healthCheckPath: /health`.
- `vercel.json` and `api/index.py`: Vercel builds the Next.js frontend and routes `/api/*` to `api/index.py`, which imports `main.app`.
- `docker-compose.yml`: local backend container on port 8000.

## Tests

- `hybrid_chatbot/tests/`: API, pipeline, coverage, and SQL bootstrap tests.
- `tests/test_service_health.py`: the `/health` payload helper.
- `perspective/tests/test_simulate_labels.py`: labelling and fallback behaviour, with the provider call stubbed.
- `globe/tests/` (run from `backend/globe`, see `pytest.ini`): `test_api.py` currently fails at collection because it imports `app.main`, which does not exist.

Run commands are in the root README.
