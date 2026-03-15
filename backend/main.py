# """
# backend/main.py — Unified NarrativeSignal API
# All modules (polarize_1, networkgraph, streamgraph2, globe, hybrid_crew)
# are mounted here under their own prefixes.

# Run from the PROJECT ROOT (one level above backend/):
#     uvicorn backend.main:app --port 8000 --host 127.0.0.1

# Or from inside backend/:
#     uvicorn main:app --port 8000 --host 127.0.0.1
# """

# import sys
# import os
# import logging
# from pathlib import Path
# from contextlib import asynccontextmanager

# import uvicorn
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware

# # ── sys.path fix ─────────────────────────────────────────────────────────────
# # Add the backend/ directory itself so sub-packages (polarize_1, networkgraph,
# # streamgraph2, globe, hybrid_crew) are importable as top-level packages.
# BACKEND_DIR = Path(__file__).resolve().parent
# if str(BACKEND_DIR) not in sys.path:
#     sys.path.insert(0, str(BACKEND_DIR))

# # ── Logging ──────────────────────────────────────────────────────────────────
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
#     datefmt="%H:%M:%S",
# )
# log = logging.getLogger("narrativesignal")

# # ── Load .env ─────────────────────────────────────────────────────────────────
# try:
#     from dotenv import load_dotenv
#     load_dotenv(BACKEND_DIR / ".env")
#     log.info("✓ .env loaded")
# except ImportError:
#     pass

# # ── Import sub-module routers / apps ─────────────────────────────────────────

# # polarize_1 — echo scores, treemap, similarity, intelligence brief
# polar_app = None
# try:
#     from polarize_1.data_loader import DataStore, DATA_DIR
#     from polarize_1.compute import (
#         get_echo_scores, get_similarity_matrix,
#         get_category_breakdown, get_top_domains,
#         get_treemap_payload, get_subreddit_summary_payload,
#         get_global_ecosystem_payload,
#     )
#     from polarize_1.ai_brief import generate_brief
#     from pydantic import BaseModel as _BM
#     import os as _os

#     _store = DataStore()
#     _store.load()
#     log.info("✓ polarize_1 data loaded — subreddits: %s", _store.subreddits)

#     class _BriefRequest(_BM):
#         subreddit: str

#     polar_app = FastAPI(title="Polarize API")
#     @polar_app.get("/subreddits")
#     def _list_subreddits():
#         return {"subreddits": _store.subreddits}

#     @polar_app.get("/echo-scores")
#     def _echo_scores():
#         return get_echo_scores(_store)

#     @polar_app.get("/similarity")
#     def _similarity():
#         return get_similarity_matrix(_store)

#     @polar_app.get("/treemap/{subreddit}")
#     def _treemap(subreddit: str):
#         from fastapi import HTTPException
#         # Handle "all" special case for global view
#         if subreddit.lower() == "all":
#             return get_global_ecosystem_payload(_store)

#         # Case-insensitive lookup
#         actual_sub = next((s for s in _store.subreddits if s.lower() == subreddit.lower()), None)
#         if not actual_sub:
#             raise HTTPException(404, f"Unknown subreddit: {subreddit}")
        
#         return get_treemap_payload(_store, actual_sub)

#     @polar_app.get("/category-breakdown/{subreddit}")
#     def _cat_breakdown(subreddit: str):
#         from fastapi import HTTPException
#         actual_sub = next((s for s in _store.subreddits if s.lower() == subreddit.lower()), None)
#         if not actual_sub:
#             raise HTTPException(404, f"Unknown subreddit: {subreddit}")
#         return {"subreddit": actual_sub, "breakdown": get_category_breakdown(_store, actual_sub)}

#     @polar_app.get("/top-domains/{subreddit}")
#     def _top_domains(subreddit: str, n: int = 5):
#         from fastapi import HTTPException
#         actual_sub = next((s for s in _store.subreddits if s.lower() == subreddit.lower()), None)
#         if not actual_sub:
#             raise HTTPException(404, f"Unknown subreddit: {subreddit}")
#         return {"subreddit": actual_sub, "domains": get_top_domains(_store, actual_sub, n)}

#     @polar_app.get("/summary-payload/{subreddit}")
#     def _summary_payload(subreddit: str):
#         from fastapi import HTTPException
#         actual_sub = next((s for s in _store.subreddits if s.lower() == subreddit.lower()), None)
#         if not actual_sub:
#             raise HTTPException(404, f"Unknown subreddit: {subreddit}")
#         return get_subreddit_summary_payload(_store, actual_sub)

#     @polar_app.post("/intelligence-brief")
#     async def _intelligence_brief(req: _BriefRequest):
#         from fastapi import HTTPException
#         actual_sub = next((s for s in _store.subreddits if s.lower() == req.subreddit.lower()), None)
#         if not actual_sub:
#             raise HTTPException(404, f"Unknown subreddit: {req.subreddit}")
#         api_key = _os.getenv("GROQ_API_KEY")
#         if not api_key:
#             raise HTTPException(500, "GROQ_API_KEY not set")
#         payload = get_subreddit_summary_payload(_store, actual_sub)
#         brief = await generate_brief(payload, api_key)
#         return {"subreddit": actual_sub, "brief": brief, "payload": payload}

#     class _DomainAnalysisRequest(_BM):
#         domain: str
#         subreddit: str = "politics"
#         category: str = "General"
#         narratives: list = []

#     @polar_app.post("/ai-analysis")
#     async def _domain_analysis(req: _DomainAnalysisRequest):
#         import json
#         from pathlib import Path
#         import httpx
#         from polarize_1.compute import get_domain_posts

#         api_key = _os.getenv("GROQ_API_KEY")
#         data_dir = Path(__file__).resolve().parent / ".." / "data"
#         cache_file = data_dir / "ai_cache.json"
        
#         # 1. Check Cache
#         cache = {}
#         if cache_file.exists():
#             try:
#                 cache = json.loads(cache_file.read_text(encoding="utf-8"))
#             except: pass
            
#         cache_key = f"{req.subreddit}:{req.domain}"
#         if cache_key in cache:
#             return {"analysis": cache[cache_key]}

#         # 2. Get Real News Context
#         titles = get_domain_posts(_store, req.subreddit, req.domain, limit=20)
#         news_context = "\n".join([f"- {t}" for t in titles[:10]]) if titles else "No specific titles found."

#         # 3. Build Detailed Prompt
#         narratives_str = ", ".join(req.narratives[:3]) if req.narratives else "various topics"
#         prompt = (
#             f"You are a media intelligence analyst. Analyzing '{req.domain}' in the context of r/{req.subreddit}.\n\n"
#             f"CATEGORY: {req.category}\n"
#             f"IDENTIFIED NARRATIVES: {narratives_str}\n\n"
#             f"RECENT POST TITLES FROM THIS SOURCE IN THIS SUBREDDIT:\n{news_context}\n\n"
#             f"TASK: Provide a concise (3-4 sentence) intelligence summary. "
#             f"Specifically: What kind of news is this source pushing in this community? "
#             f"What is the general sentiment of these headlines (e.g., alarmist, neutral, celebratory, critical)? "
#             f"How does it shape the community's perspective?"
#         )

#         analysis = ""
#         if api_key:
#             try:
#                 async with httpx.AsyncClient(timeout=15.0) as client:
#                     resp = await client.post(
#                         "https://api.groq.com/openai/v1/chat/completions",
#                         headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
#                         json={
#                             "model": "llama-3.1-8b-instant",
#                             "messages": [{"role": "user", "content": prompt}],
#                             "max_tokens": 300,
#                         },
#                     )
#                     if resp.status_code == 200:
#                         data = resp.json()
#                         analysis = data["choices"][0]["message"]["content"].strip()
#             except Exception as e:
#                 log.warning("Groq domain analysis failed: %s", e)

#         # 4. Fallback if no API key or failed
#         if not analysis:
#             traits = {
#                 "News": "major news outlet framing",
#                 "Blogs": "independent perspective",
#                 "Advocacy": "partisan advocacy",
#                 "Video": "multimedia engagement"
#             }
#             short_trait = traits.get(req.category, "digital influence")
#             analysis = (
#                 f"{req.domain} serves as a primary {short_trait} for r/{req.subreddit}. "
#                 f"The community engages with it primarily around {narratives_str}, "
#                 f"indicating a reliance on its specific editorial framing for these topics."
#             )

#         # 5. Save to Cache
#         cache[cache_key] = analysis
#         try:
#             cache_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
#         except: pass

#         return {"analysis": analysis}

#         # Deterministic fallback
#         category_traits = {
#             "News": "a major news outlet with broad audience reach and editorial influence",
#             "Blogs": "an independent publishing platform with niche editorial perspectives",
#             "Advocacy": "an advocacy-driven publication with a focused policy agenda",
#             "Research": "a research institution that produces data-driven, peer-reviewed analysis",
#             "Government": "an official government source providing authoritative policy information",
#         }
#         trait = category_traits.get(req.category, "a notable online media source")
#         return {
#             "analysis": (
#                 f"{req.domain} is {trait}. "
#                 f"Its primary narratives span {narratives_str}, making it a significant signal source in the {req.category} ecosystem. "
#                 f"High community reference volumes indicate strong audience engagement and topic resonance across political communities."
#             )
#         }

#     log.info("✓ polarize_1 routes registered")
# except Exception as e:
#     log.warning("Could not load polarize_1: %s", e)
#     polar_app = FastAPI()


# # networkgraph — graph, transport, narrative, user, analyze routers
# network_app = None
# try:
#     from networkgraph.data.loader import load_all as _ng_load_all, get_store as _ng_get_store
#     from networkgraph.routers import graph, transport, narrative, user, analyze
#     from contextlib import asynccontextmanager as _acm

#     _ng_load_all()

#     @_acm
#     async def _ng_lifespan(app):
#         log.info("✓ networkgraph data loaded — %s", _ng_get_store().row_counts())
#         yield

#     network_app = FastAPI(title="NetworkGraph API", lifespan=_ng_lifespan)
#     network_app.include_router(graph.router)
#     network_app.include_router(transport.router)
#     network_app.include_router(narrative.router)
#     network_app.include_router(user.router)
#     network_app.include_router(analyze.router)

#     @network_app.get("/health")
#     def _ng_health():
#         s = _ng_get_store()
#         return {"status": "ok" if s.ready else "loading", "datasets": s.row_counts()}

#     log.info("✓ networkgraph routes registered")
# except Exception as e:
#     log.warning("Could not load networkgraph: %s", e)
#     network_app = FastAPI()


# # streamgraph2 — ecosystem + spike routers
# stream_app = None
# try:
#     from streamgraph2.data import db as _sg_db
#     from streamgraph2.routers import ecosystem, spike, cluster
#     from contextlib import asynccontextmanager as _acm2

#     @_acm2
#     async def _sg_lifespan(app):
#         import asyncio
#         for attempt in range(1, 4):
#             try:
#                 await _sg_db.init_pool()
#                 log.info("✓ streamgraph2 DB pool ready")
#                 break
#             except Exception as e:
#                 if attempt < 3:
#                     log.warning("  streamgraph2 DB retry %d/3: %s", attempt, e)
#                     await asyncio.sleep(2)
#                 else:
#                     log.error("  streamgraph2 DB failed after 3 attempts")
#                     raise
#         yield
#         await _sg_db.close_pool()

#     stream_app = FastAPI(title="Streamgraph API", lifespan=_sg_lifespan)
#     stream_app.include_router(ecosystem.router, prefix="/api")
#     stream_app.include_router(spike.router, prefix="/api")
#     stream_app.include_router(cluster.router, prefix="/api")

#     @stream_app.get("/health")
#     async def _sg_health():
#         return {"status": "ok", "module": "streamgraph2"}

#     log.info("✓ streamgraph2 routes registered")
# except Exception as e:
#     log.warning("Could not load streamgraph2: %s", e)
#     stream_app = FastAPI()


# # globe — events, pipeline, health routers
# globe_app = None
# try:
#     from globe.app.config import get_settings as _g_settings
#     from globe.app.database.connection import init_db as _g_init, close_db as _g_close
#     from globe.app.api.routes import events as _g_events, pipeline as _g_pipeline, health as _g_health
#     from pathlib import Path as _Path
#     from contextlib import asynccontextmanager as _acm3

#     _gsettings = _g_settings()

#     @_acm3
#     async def _globe_lifespan(app):
#         _Path(_gsettings.DATA_DIR).mkdir(exist_ok=True)
#         _Path(_gsettings.LOG_DIR).mkdir(exist_ok=True)
#         _g_init()
#         log.info("✓ globe DB initialised")
#         yield
#         _g_close()

#     globe_app = FastAPI(title="Globe API", lifespan=_globe_lifespan)
#     globe_app.include_router(_g_health.router)
#     globe_app.include_router(_g_events.router)
#     globe_app.include_router(_g_pipeline.router)
#     log.info("✓ globe routes registered")
# except Exception as e:
#     log.warning("Could not load globe: %s", e)
#     globe_app = FastAPI()


# # hybrid_crew — research pipeline
# hybrid_app = None
# try:
#     from hybrid_crew.pipeline import run_pipeline_sync as _run_pipeline
#     from pydantic import BaseModel as _HBM
#     from fastapi import HTTPException as _HE
#     import asyncio as _asyncio
#     import concurrent.futures as _cf

#     class _HQueryRequest(_HBM):
#         query: str

#     hybrid_app = FastAPI(title="Hybrid Crew API")

#     @hybrid_app.post("/api/query")
#     async def _hc_query(payload: _HQueryRequest):
#         if not payload.query.strip():
#             raise _HE(400, "Query cannot be empty.")
#         loop = _asyncio.get_event_loop()
#         with _cf.ThreadPoolExecutor() as pool:
#             result = await loop.run_in_executor(pool, _run_pipeline, payload.query)
#         return result

#     @hybrid_app.get("/health")
#     async def _hc_health():
#         return {"status": "ok", "pipeline": "hybrid_crew v2"}

#     log.info("✓ hybrid_crew routes registered")
# except Exception as e:
#     log.warning("Could not load hybrid_crew: %s", e)
#     hybrid_app = FastAPI()


# # ── Unified App ───────────────────────────────────────────────────────────────
# # Mounted sub-apps do NOT have their lifespan triggered by Starlette.
# # We use the parent app's lifespan to initialise resources for all sub-modules.

# @asynccontextmanager
# async def _main_lifespan(application: FastAPI):
#     # streamgraph2 — init DB pool (sub-app lifespan never fires when mounted).
#     # init_pool() handles a missing DATABASE_URL gracefully; CSV fallback activates.
#     try:
#         from streamgraph2.data import db as _sg_db2
#         await _sg_db2.init_pool()
#         log.info("✓ streamgraph2 init_pool() called (main lifespan)")
#     except ImportError as e:
#         log.warning("streamgraph2 not available: %s", e)
#     except Exception as e:
#         log.warning("streamgraph2 pool init error (CSV fallback active): %s", e)

#     yield

#     # Cleanup
#     try:
#         from streamgraph2.data import db as _sg_db2
#         await _sg_db2.close_pool()
#     except Exception:
#         pass


# app = FastAPI(
#     title="NarrativeSignal — Unified API",
#     description="Master entry point for all NarrativeSignal backend modules.",
#     version="2.0.0",
#     lifespan=_main_lifespan,
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Mount each module under its prefix
# # Frontend proxy (next.config.js) rewrites /api/* → localhost:8000/*
# # So these are accessible at /api/polar/*, /api/network/*, etc.
# app.mount("/api/polar", polar_app)
# app.mount("/api/network", network_app)
# app.mount("/api/stream", stream_app)
# app.mount("/api/globe", globe_app)
# app.mount("/api/hybrid", hybrid_app)

# # Convenience top-level shortcuts used by the Polar dashboard frontend
# # (frontend calls /api/subreddits, /api/treemap/:sub, etc.)
# app.mount("/api", polar_app)


# @app.get("/", include_in_schema=False)
# def root():
#     return {
#         "service": "NarrativeSignal Unified Backend",
#         "version": "2.0.0",
#         "docs": "/docs",
#         "modules": {
#             "polarize": "/api/polar — or shortcut /api/subreddits, /api/treemap/:sub …",
#             "network":  "/api/network",
#             "stream":   "/api/stream",
#             "globe":    "/api/globe",
#             "hybrid":   "/api/hybrid",
#         },
#     }


# if __name__ == "__main__":
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


"""
backend/main.py — Unified NarrativeSignal API
All modules (polarize_1, networkgraph, streamgraph2, globe, hybrid_crew)
are mounted here under their own prefixes.

Run from the PROJECT ROOT (one level above backend/):
    uvicorn backend.main:app --port 8000 --host 127.0.0.1

Or from inside backend/:
    uvicorn main:app --port 8000 --host 127.0.0.1
"""

import sys
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── sys.path fix ─────────────────────────────────────────────────────────────
# Add the backend/ directory itself so sub-packages (polarize_1, networkgraph,
# streamgraph2, globe, hybrid_crew) are importable as top-level packages.
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("narrativesignal")

# ── Load .env ─────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
    log.info("✓ .env loaded")
except ImportError:
    pass

# ── Import sub-module routers / apps ─────────────────────────────────────────

# polarize_1 — echo scores, treemap, similarity, intelligence brief
polar_app = None
try:
    from polarize_1.data_loader import DataStore, DATA_DIR
    from polarize_1.compute import (
        get_echo_scores, get_similarity_matrix,
        get_category_breakdown, get_top_domains,
        get_treemap_payload, get_subreddit_summary_payload,
        get_global_ecosystem_payload,
    )
    from polarize_1.ai_brief import generate_brief
    from pydantic import BaseModel as _BM
    import os as _os

    _store = DataStore()
    _store.load()
    log.info("✓ polarize_1 data loaded — subreddits: %s", _store.subreddits)

    class _BriefRequest(_BM):
        subreddit: str

    polar_app = FastAPI(title="Polarize API")
    @polar_app.get("/subreddits")
    def _list_subreddits():
        return {"subreddits": _store.subreddits}

    @polar_app.get("/echo-scores")
    def _echo_scores():
        return get_echo_scores(_store)

    @polar_app.get("/similarity")
    def _similarity():
        return get_similarity_matrix(_store)

    @polar_app.get("/treemap/{subreddit}")
    def _treemap(subreddit: str):
        from fastapi import HTTPException
        # Handle "all" special case for global view
        if subreddit.lower() == "all":
            return get_global_ecosystem_payload(_store)

        # Case-insensitive lookup
        actual_sub = next((s for s in _store.subreddits if s.lower() == subreddit.lower()), None)
        if not actual_sub:
            raise HTTPException(404, f"Unknown subreddit: {subreddit}")
        
        return get_treemap_payload(_store, actual_sub)

    @polar_app.get("/category-breakdown/{subreddit}")
    def _cat_breakdown(subreddit: str):
        from fastapi import HTTPException
        actual_sub = next((s for s in _store.subreddits if s.lower() == subreddit.lower()), None)
        if not actual_sub:
            raise HTTPException(404, f"Unknown subreddit: {subreddit}")
        return {"subreddit": actual_sub, "breakdown": get_category_breakdown(_store, actual_sub)}

    @polar_app.get("/top-domains/{subreddit}")
    def _top_domains(subreddit: str, n: int = 5):
        from fastapi import HTTPException
        actual_sub = next((s for s in _store.subreddits if s.lower() == subreddit.lower()), None)
        if not actual_sub:
            raise HTTPException(404, f"Unknown subreddit: {subreddit}")
        return {"subreddit": actual_sub, "domains": get_top_domains(_store, actual_sub, n)}

    @polar_app.get("/summary-payload/{subreddit}")
    def _summary_payload(subreddit: str):
        from fastapi import HTTPException
        actual_sub = next((s for s in _store.subreddits if s.lower() == subreddit.lower()), None)
        if not actual_sub:
            raise HTTPException(404, f"Unknown subreddit: {subreddit}")
        return get_subreddit_summary_payload(_store, actual_sub)

    @polar_app.post("/intelligence-brief")
    async def _intelligence_brief(req: _BriefRequest):
        from fastapi import HTTPException
        actual_sub = next((s for s in _store.subreddits if s.lower() == req.subreddit.lower()), None)
        if not actual_sub:
            raise HTTPException(404, f"Unknown subreddit: {req.subreddit}")
        api_key = _os.getenv("GROQ_API_KEY")
        if not api_key:
            raise HTTPException(500, "GROQ_API_KEY not set")
        payload = get_subreddit_summary_payload(_store, actual_sub)
        brief = await generate_brief(payload, api_key)
        return {"subreddit": actual_sub, "brief": brief, "payload": payload}

    class _DomainAnalysisRequest(_BM):
        domain: str
        subreddit: str = "politics"
        category: str = "General"
        narratives: list = []

    @polar_app.post("/ai-analysis")
    async def _domain_analysis(req: _DomainAnalysisRequest):
        import json
        from pathlib import Path
        import httpx
        from polarize_1.compute import get_domain_posts

        api_key = _os.getenv("GROQ_API_KEY")
        data_dir = Path(__file__).resolve().parent / ".." / "data"
        cache_file = data_dir / "ai_cache.json"
        
        # 1. Check Cache
        cache = {}
        if cache_file.exists():
            try:
                cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except: pass
            
        cache_key = f"{req.subreddit}:{req.domain}"
        if cache_key in cache:
            return {"analysis": cache[cache_key]}

        # 2. Get Real News Context
        titles = get_domain_posts(_store, req.subreddit, req.domain, limit=20)
        news_context = "\n".join([f"- {t}" for t in titles[:10]]) if titles else "No specific titles found."

        # 3. Build Detailed Prompt
        narratives_str = ", ".join(req.narratives[:3]) if req.narratives else "various topics"
        prompt = (
            f"You are a media intelligence analyst. Analyzing '{req.domain}' in the context of r/{req.subreddit}.\n\n"
            f"CATEGORY: {req.category}\n"
            f"IDENTIFIED NARRATIVES: {narratives_str}\n\n"
            f"RECENT POST TITLES FROM THIS SOURCE IN THIS SUBREDDIT:\n{news_context}\n\n"
            f"TASK: Provide a concise (3-4 sentence) intelligence summary. "
            f"Specifically: What kind of news is this source pushing in this community? "
            f"What is the general sentiment of these headlines (e.g., alarmist, neutral, celebratory, critical)? "
            f"How does it shape the community's perspective?"
        )

        analysis = ""
        if api_key:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": "llama-3.1-8b-instant",
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 300,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        analysis = data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                log.warning("Groq domain analysis failed: %s", e)

        # 4. Fallback if no API key or failed
        if not analysis:
            traits = {
                "News": "major news outlet framing",
                "Blogs": "independent perspective",
                "Advocacy": "partisan advocacy",
                "Video": "multimedia engagement"
            }
            short_trait = traits.get(req.category, "digital influence")
            analysis = (
                f"{req.domain} serves as a primary {short_trait} for r/{req.subreddit}. "
                f"The community engages with it primarily around {narratives_str}, "
                f"indicating a reliance on its specific editorial framing for these topics."
            )

        # 5. Save to Cache
        cache[cache_key] = analysis
        try:
            cache_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        except: pass

        return {"analysis": analysis}
        # FIX 4: Removed unreachable dead code block that was here after the return

    log.info("✓ polarize_1 routes registered")
except Exception as e:
    log.warning("Could not load polarize_1: %s", e)
    polar_app = FastAPI()


# networkgraph — graph, transport, narrative, user, analyze routers
network_app = None
try:
    from networkgraph.routers import intelligence, narratives

    network_app = FastAPI(title="NetworkGraph API")
    network_app.include_router(intelligence.router)
    network_app.include_router(narratives.router)

    @network_app.get("/health")
    def _ng_health():
        db_path = BACKEND_DIR / ".." / "data" / "analysis_v2.db"
        return {
            "status": "ok" if db_path.exists() else "missing-db",
            "database": str(db_path.resolve()),
            "exists": db_path.exists(),
            "mode": "db-backed-intelligence-only",
        }

    log.info("✓ networkgraph routes registered: %s",
             [r.path for r in network_app.routes if hasattr(r, "path")])
except Exception as e:
    log.exception("✗ Could not load networkgraph (falling back to empty app):")
    network_app = FastAPI()


# streamgraph2 — ecosystem + spike routers
stream_app = None
try:
    from streamgraph2.data import db as _sg_db
    from streamgraph2.routers import ecosystem, spike, cluster
    from contextlib import asynccontextmanager as _acm2

    @_acm2
    async def _sg_lifespan(app):
        import asyncio
        for attempt in range(1, 4):
            try:
                await _sg_db.init_pool()
                log.info("✓ streamgraph2 DB pool ready")
                break
            except Exception as e:
                if attempt < 3:
                    log.warning("  streamgraph2 DB retry %d/3: %s", attempt, e)
                    await asyncio.sleep(2)
                else:
                    log.error("  streamgraph2 DB failed after 3 attempts")
                    raise
        yield
        await _sg_db.close_pool()

    stream_app = FastAPI(title="Streamgraph API", lifespan=_sg_lifespan)
    stream_app.include_router(ecosystem.router, prefix="/api")
    stream_app.include_router(spike.router, prefix="/api")
    stream_app.include_router(cluster.router, prefix="/api")

    @stream_app.get("/health")
    async def _sg_health():
        return {"status": "ok", "module": "streamgraph2"}

    log.info("✓ streamgraph2 routes registered")
except Exception as e:
    log.warning("Could not load streamgraph2: %s", e)
    stream_app = FastAPI()


# globe — events, pipeline, health routers
globe_app = None
try:
    GLOBE_DIR = BACKEND_DIR / "globe"
    if str(GLOBE_DIR) not in sys.path:
        sys.path.insert(0, str(GLOBE_DIR))

    from globe.app.config import get_settings as _g_settings
    from globe.app.database.connection import init_db as _g_init, close_db as _g_close
    from globe.app.api.routes import events as _g_events, pipeline as _g_pipeline, health as _g_health
    from pathlib import Path as _Path
    from contextlib import asynccontextmanager as _acm3

    _gsettings = _g_settings()

    @_acm3
    async def _globe_lifespan(app):
        _Path(_gsettings.DATA_DIR).mkdir(exist_ok=True)
        _Path(_gsettings.LOG_DIR).mkdir(exist_ok=True)
        _g_init()
        log.info("✓ globe DB initialised")
        yield
        _g_close()

    globe_app = FastAPI(title="Globe API", lifespan=_globe_lifespan)
    globe_app.include_router(_g_health.router)
    globe_app.include_router(_g_events.router)
    globe_app.include_router(_g_pipeline.router)
    log.info("✓ globe routes registered")
except Exception as e:
    log.warning("Could not load globe: %s", e)
    globe_app = FastAPI()


# hybrid_crew — research pipeline
hybrid_app = None
try:
    from hybrid_crew.pipeline import run_pipeline_sync as _run_pipeline
    from pydantic import BaseModel as _HBM
    from fastapi import HTTPException as _HE
    import asyncio as _asyncio
    import concurrent.futures as _cf

    class _HQueryRequest(_HBM):
        query: str

    hybrid_app = FastAPI(title="Hybrid Crew API")

    @hybrid_app.post("/api/query")
    async def _hc_query(payload: _HQueryRequest):
        if not payload.query.strip():
            raise _HE(400, "Query cannot be empty.")
        loop = _asyncio.get_event_loop()
        with _cf.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(pool, _run_pipeline, payload.query)
        return result

    @hybrid_app.get("/health")
    async def _hc_health():
        return {"status": "ok", "pipeline": "hybrid_crew v2"}

    log.info("✓ hybrid_crew routes registered")
except Exception as e:
    log.warning("Could not load hybrid_crew: %s", e)
    hybrid_app = FastAPI()


# hybrid_chatbot — deployable SQL + embeddings chatbot
hybrid_chat_app = None
try:
    from hybrid_chatbot.api import app as hybrid_chat_app
    log.info("✓ hybrid_chatbot routes registered")
except Exception as e:
    log.warning("Could not load hybrid_chatbot: %s", e)
    hybrid_chat_app = FastAPI()


# perspective — persona reaction simulator
perspective_app = None
try:
    from perspective.routes.perspective_routes import router as _perspective_router

    perspective_app = FastAPI(title="Perspective Simulator API")
    perspective_app.include_router(_perspective_router)
    log.info("✓ perspective routes registered")  # FIX 1: corrected indentation
except Exception as e:
    log.warning("Could not load perspective: %s", e)
    perspective_app = FastAPI()


# ── Main app + CORS ───────────────────────────────────────────────────────────
# FIX 2 + 3: Added the missing app = FastAPI() definition and the complete
# add_middleware() call. The orphaned allow_methods/allow_headers lines
# are replaced by this single correctly-formed call.

@asynccontextmanager
async def _main_lifespan(application: FastAPI):
    # streamgraph2 — init DB pool
    try:
        from streamgraph2.data import db as _sg_db2
        await _sg_db2.init_pool()
        log.info("✓ streamgraph2 init_pool() called (main lifespan)")
    except ImportError as e:
        log.warning("streamgraph2 not available: %s", e)
    except Exception as e:
        log.warning("streamgraph2 pool init error: %s", e)

    # hybrid_chatbot — initialize SQL + vector index
    try:
        from hybrid_chatbot.api import init_resources as _hc_init
        _hc_init()
        log.info("✓ hybrid_chatbot resources initialised")
    except Exception as e:
        log.warning("hybrid_chatbot init failed: %s", e)

    # globe — initialize duckdb tables
    try:
        from globe.app.config import get_settings as _g_settings
        from globe.app.database.connection import init_db as _g_init
        from pathlib import Path as _Path
        _gsettings = _g_settings()
        _Path(_gsettings.DATA_DIR).mkdir(exist_ok=True)
        _Path(_gsettings.LOG_DIR).mkdir(exist_ok=True)
        _g_init()
        log.info("✓ globe DB tables initialised")
    except ImportError as e:
        log.warning("globe fallback not available: %s", e)
    except Exception as e:
        log.warning("globe init failed: %s", e)

    yield

    # Cleanup
    try:
        from streamgraph2.data import db as _sg_db2
        await _sg_db2.close_pool()
    except Exception:
        pass


app = FastAPI(title="NarrativeSignal Unified API", lifespan=_main_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount each module under its prefix
# Frontend proxy (next.config.js) rewrites /api/* → localhost:8000/*
# So these are accessible at /api/polar/*, /api/network/*, etc.
app.mount("/api/polar", polar_app)
app.mount("/api/network", network_app)
app.mount("/api/stream", stream_app)
app.mount("/api/globe", globe_app)
app.mount("/api/hybrid", hybrid_app)
app.mount("/api/chatbot", hybrid_chat_app)
app.mount("/api/perspective", perspective_app)

# Convenience top-level shortcuts used by the Polar dashboard frontend
# (frontend calls /api/subreddits, /api/treemap/:sub, etc.)
app.mount("/api", polar_app)


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "NarrativeSignal Unified Backend",
        "version": "2.0.0",
        "docs": "/docs",
        "modules": {
            "polarize": "/api/polar — or shortcut /api/subreddits, /api/treemap/:sub …",
            "network":  "/api/network",
            "stream":   "/api/stream",
            "globe":    "/api/globe",
            "hybrid":   "/api/hybrid",
            "chatbot": "/api/chatbot",
            "perspective": "/api/perspective",
        },
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
