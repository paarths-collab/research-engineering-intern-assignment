"""
test_all.py — Full test suite for the Catalyst Intelligence Platform backend.

Covers all 19 modules:
  config.py, db.py, embedder.py, ingest.py, llm_engine.py,
  main.py, matcher.py, media_ecosystem.py, news_fetcher.py,
  pipeline.py, reddit_ingest.py, sentiment_engine.py, topic_engine.py,
  agents/__init__.py, agents/anomaly_agent.py, agents/repair_agent.py,
  agents/report_agent.py, agents/supervisor.py, agents/validator_agent.py

Run:
    pip install pytest pytest-asyncio httpx
    pytest test_all.py -v

No real DB, no real API keys, no network needed.
All external dependencies are mocked.
"""

import asyncio
import importlib
import math
import os
import sys
import types
import unittest
from datetime import date, datetime
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# ── Path setup so all modules resolve ────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ── Inject stub env vars BEFORE config is imported ───────────
os.environ.setdefault("DATABASE_URL",        "postgresql://user:pass@ep-real-host.us-east-2.aws.neon.tech/neondb?sslmode=require")
os.environ.setdefault("GROQ_API_KEY", "gsk-test-key-000000000000")
os.environ.setdefault("REDDIT_CLIENT_ID",    "test_id")
os.environ.setdefault("REDDIT_CLIENT_SECRET","test_secret")
os.environ.setdefault("NEWSAPI_KEY",         "test_newsapi")


# ═════════════════════════════════════════════════════════════
# FIXTURES & SHARED HELPERS
# ═════════════════════════════════════════════════════════════

def _make_vec(n: int = 384, val: float = 0.1) -> List[float]:
    """Return a normalised-ish vector of length n."""
    v = [val] * n
    mag = math.sqrt(sum(x * x for x in v))
    return [x / mag for x in v]


def _make_pipeline_result(
    n_topics: int = 2,
    sim: float = 0.75,
    neg: float = 30.0,
    neu: float = 40.0,
    pos: float = 30.0,
    accel: float = 3.5,
) -> dict:
    """Build a realistic-looking pipeline result dict."""
    topics = [
        {"topic_id": i, "size": 50, "size_percent": 50.0 / n_topics,
         "keywords": ["word1", "word2"], "centroid": _make_vec()}
        for i in range(n_topics)
    ]
    matches = [
        {"topic_id": 0, "headline": f"News headline {i}",
         "source": "TestSource", "url": "http://example.com",
         "similarity": sim}
        for i in range(6)
    ]
    sentiment = [
        {"date": "2025-02-13", "negative": neg,     "neutral": neu,     "positive": pos},
        {"date": "2025-02-14", "negative": neg + 5, "neutral": neu - 3, "positive": pos - 2},
        {"date": "2025-02-15", "negative": neg + 2, "neutral": neu,     "positive": pos - 2},
    ]
    return {
        "spike_date": "2025-02-14",
        "topics"    : topics,
        "news_matches": matches,
        "sentiment" : sentiment,
        "metrics"   : {
            "baseline_count"    : 100,
            "spike_count"       : 350,
            "acceleration_ratio": accel,
        },
    }


# ═════════════════════════════════════════════════════════════
# 1. config.py
# ═════════════════════════════════════════════════════════════

class TestConfig(unittest.TestCase):

    def test_imports_cleanly(self):
        import config
        self.assertIsNotNone(config)

    def test_required_vars_present(self):
        import config
        self.assertIsInstance(config.DATABASE_URL, str)
        self.assertIsInstance(config.GROQ_API_KEY, str)

    def test_defaults_are_correct_types(self):
        import config
        self.assertIsInstance(config.SPIKE_Z_THRESHOLD, float)
        self.assertIsInstance(config.BERTOPIC_MIN_TOPIC, int)
        self.assertIsInstance(config.NEWS_FETCH_LIMIT, int)
        self.assertIsInstance(config.SIMILARITY_TOP_K, int)
        self.assertIsInstance(config.EMBEDDING_DIM, int)
        self.assertEqual(config.EMBEDDING_DIM, 384)

    def test_agent_thresholds_are_floats(self):
        import config
        self.assertIsInstance(config.AGENT_MIN_SIMILARITY, float)
        self.assertIsInstance(config.AGENT_WARN_SIMILARITY, float)
        self.assertIsInstance(config.AGENT_MAX_DOMINANT_TOPIC, float)

    def test_placeholder_detection(self):
        """Config should reject placeholder DATABASE_URL values."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@ep-xxx.neon.tech/db"}):
            with self.assertRaises(EnvironmentError):
                import importlib
                import config as cfg
                importlib.reload(cfg)

    def test_missing_key_raises(self):
        env = {k: v for k, v in os.environ.items() if k != "GROQ_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(EnvironmentError):
                import config as cfg
                importlib.reload(cfg)


# ═════════════════════════════════════════════════════════════
# 2. db.py  (unit-level — no real connection)
# ═════════════════════════════════════════════════════════════

class TestDb(unittest.TestCase):

    def test_vec_to_pg_roundtrip(self):
        import db
        original = [0.1, 0.2, 0.3, -0.4]
        pg_str   = db.vec_to_pg(original)
        self.assertTrue(pg_str.startswith("["))
        self.assertTrue(pg_str.endswith("]"))
        result = db.pg_to_vec(pg_str)
        for a, b in zip(original, result):
            self.assertAlmostEqual(a, b, places=6)

    def test_vec_to_pg_format(self):
        import db
        result = db.vec_to_pg([1.0, 2.0, 3.0])
        self.assertEqual(result, "[1.0,2.0,3.0]")

    def test_pg_to_vec_parses_brackets(self):
        import db
        result = db.pg_to_vec("[0.5,0.5,0.0]")
        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result[0], 0.5)

    def test_pg_to_vec_handles_negatives(self):
        import db
        result = db.pg_to_vec("[-0.1,0.2,-0.3]")
        self.assertAlmostEqual(result[0], -0.1)
        self.assertAlmostEqual(result[2], -0.3)

    def test_module_has_required_functions(self):
        import db
        required = [
            "init_pool", "close_pool", "upsert_post", "upsert_comment",
            "get_posts_for_date", "count_posts_for_date",
            "get_texts_for_date", "upsert_volume", "get_volume_series",
            "create_spike_job", "update_job_status", "get_job",
            "get_full_job_result", "save_topic", "get_topic_centroids",
            "save_news_item", "get_news_for_date", "save_news_match",
            "save_sentiment", "save_spike_metrics", "save_brief",
            "save_diagnostic",
        ]
        for fn in required:
            self.assertTrue(hasattr(db, fn), f"db.{fn} is missing")


# ═════════════════════════════════════════════════════════════
# 3. embedder.py
# ═════════════════════════════════════════════════════════════

class TestEmbedder(unittest.TestCase):

    def test_embed_function_exists(self):
        import embedder
        self.assertTrue(callable(embedder.embed))
        self.assertTrue(callable(embedder.get_embedder))

    @patch("embedder.SentenceTransformer")
    def test_get_embedder_returns_singleton(self, MockST):
        import embedder
        # Reset singleton
        embedder._model = None
        mock_model = MagicMock()
        MockST.return_value = mock_model

        m1 = embedder.get_embedder()
        m2 = embedder.get_embedder()
        self.assertIs(m1, m2)
        MockST.assert_called_once()

    @patch("embedder.SentenceTransformer")
    def test_embed_returns_list(self, MockST):
        import embedder
        embedder._model = None
        mock_model = MagicMock()
        mock_model.encode.return_value = [[0.1] * 384, [0.2] * 384]
        MockST.return_value = mock_model

        result = embedder.embed(["hello", "world"])
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)


# ═════════════════════════════════════════════════════════════
# 4. matcher.py — _cosine (pure function, no DB needed)
# ═════════════════════════════════════════════════════════════

class TestMatcher(unittest.TestCase):

    def _cosine(self, a, b):
        """Mirror of the private function for test assertions."""
        from matcher import _cosine
        return _cosine(a, b)

    def test_identical_vectors_give_1(self):
        v = [0.5, 0.5, 0.5, 0.5]
        self.assertAlmostEqual(self._cosine(v, v), 1.0, places=6)

    def test_orthogonal_vectors_give_0(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(self._cosine(a, b), 0.0, places=6)

    def test_opposite_vectors_give_neg1(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        self.assertAlmostEqual(self._cosine(a, b), -1.0, places=6)

    def test_zero_vector_returns_0(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        self.assertEqual(self._cosine(a, b), 0.0)
        self.assertEqual(self._cosine(b, a), 0.0)

    def test_similarity_is_symmetric(self):
        a = [0.3, 0.7, 0.1]
        b = [0.9, 0.1, 0.5]
        self.assertAlmostEqual(self._cosine(a, b), self._cosine(b, a), places=6)

    def test_result_bounded_minus1_to_1(self):
        import random
        random.seed(42)
        for _ in range(20):
            a = [random.gauss(0, 1) for _ in range(10)]
            b = [random.gauss(0, 1) for _ in range(10)]
            sim = self._cosine(a, b)
            self.assertGreaterEqual(sim, -1.0 - 1e-9)
            self.assertLessEqual(sim, 1.0 + 1e-9)

    @pytest.mark.asyncio
    async def test_run_similarity_matching_empty_inputs(self):
        from matcher import run_similarity_matching
        result = await run_similarity_matching("job-1", [], [])
        self.assertEqual(result, [])

    @pytest.mark.asyncio
    async def test_run_similarity_matching_returns_top_k(self):
        from matcher import run_similarity_matching
        import config

        topic = {"topic_id": 0, "centroid": [1.0, 0.0, 0.0]}
        news = [
            {"headline": f"h{i}", "source": "s", "url": "u",
             "embedding": [0.9 - i * 0.1, 0.1, 0.1]}
            for i in range(10)
        ]
        with patch("matcher.db.save_news_match", new_callable=AsyncMock):
            results = await run_similarity_matching("job-1", [topic], news)
        self.assertLessEqual(len(results), config.SIMILARITY_TOP_K)

    @pytest.mark.asyncio
    async def test_run_similarity_matching_sorted_descending(self):
        from matcher import run_similarity_matching

        topic = {"topic_id": 0, "centroid": [1.0, 0.0]}
        news = [
            {"headline": "low",  "source": "s", "url": "u", "embedding": [0.1, 0.9]},
            {"headline": "high", "source": "s", "url": "u", "embedding": [0.9, 0.1]},
            {"headline": "mid",  "source": "s", "url": "u", "embedding": [0.6, 0.4]},
        ]
        with patch("matcher.db.save_news_match", new_callable=AsyncMock):
            with patch("matcher.SIMILARITY_TOP_K", 3):
                results = await run_similarity_matching("job-1", [topic], news)

        sims = [r["similarity"] for r in results]
        self.assertEqual(sims, sorted(sims, reverse=True))


# ═════════════════════════════════════════════════════════════
# 5. agents/validator_agent.py
# ═════════════════════════════════════════════════════════════

class TestValidatorAgent(unittest.TestCase):

    def setUp(self):
        from agents import validator_agent
        self.v = validator_agent

    def test_clean_result_passes(self):
        result = self.v.validate(_make_pipeline_result())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["issues"], [])
        self.assertTrue(result["passed"])

    def test_no_topics_fails(self):
        r = _make_pipeline_result()
        r["topics"] = []
        result = self.v.validate(r)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("NO_TOPICS" in i for i in result["issues"]))

    def test_no_matches_fails(self):
        r = _make_pipeline_result()
        r["news_matches"] = []
        result = self.v.validate(r)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("NO_MATCHES" in i for i in result["issues"]))

    def test_all_low_similarity_fails(self):
        r = _make_pipeline_result(sim=0.1)
        result = self.v.validate(r)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("LOW_SIMILARITY" in i for i in result["issues"]))

    def test_bad_sentiment_sum_warns(self):
        r = _make_pipeline_result()
        r["sentiment"] = [{"date": "2025-02-14", "negative": 10, "neutral": 10, "positive": 10}]
        result = self.v.validate(r)
        self.assertIn("SENTIMENT_SUM_ERROR", " ".join(result["issues"]))

    def test_no_acceleration_warns(self):
        r = _make_pipeline_result()
        r["metrics"] = {}
        result = self.v.validate(r)
        self.assertTrue(any("NO_ACCELERATION" in i for i in result["issues"]))

    def test_zero_size_topic_warns(self):
        r = _make_pipeline_result()
        r["topics"][0]["size"] = 0
        result = self.v.validate(r)
        self.assertIn(result["status"], ("warn", "fail"))

    def test_low_news_count_warns(self):
        r = _make_pipeline_result()
        r["news_matches"] = [
            {"headline": "only one", "source": "s", "url": "u", "similarity": 0.9}
        ]
        result = self.v.validate(r)
        self.assertTrue(any("LOW_NEWS_COUNT" in i or "fail" == result["status"]
                            for i in result["issues"]))

    def test_returns_correct_agent_name(self):
        result = self.v.validate(_make_pipeline_result())
        self.assertEqual(result["agent"], "validator")


# ═════════════════════════════════════════════════════════════
# 6. agents/anomaly_agent.py
# ═════════════════════════════════════════════════════════════

class TestAnomalyAgent(unittest.TestCase):

    def setUp(self):
        from agents import anomaly_agent
        self.a = anomaly_agent

    def test_clean_result_is_pass(self):
        result = self.a.detect_anomalies(_make_pipeline_result())
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["clean"])

    def test_dominant_topic_warns(self):
        r = _make_pipeline_result(n_topics=1)
        r["topics"][0]["size_percent"] = 95.0
        result = self.a.detect_anomalies(r)
        self.assertEqual(result["status"], "warn")
        codes = [a["code"] for a in result["anomalies"]]
        self.assertIn("DOMINANT_TOPIC", codes)

    def test_single_topic_warns(self):
        r = _make_pipeline_result(n_topics=1)
        r["topics"][0]["size_percent"] = 50.0
        result = self.a.detect_anomalies(r)
        codes = [a["code"] for a in result["anomalies"]]
        self.assertIn("SINGLE_TOPIC", codes)

    def test_low_avg_similarity_warns(self):
        r = _make_pipeline_result(sim=0.3)
        result = self.a.detect_anomalies(r)
        codes = [a["code"] for a in result["anomalies"]]
        self.assertIn("LOW_AVERAGE_SIMILARITY", codes)

    def test_very_low_max_similarity_fails(self):
        r = _make_pipeline_result(sim=0.1)
        result = self.a.detect_anomalies(r)
        self.assertEqual(result["status"], "fail")
        codes = [a["code"] for a in result["anomalies"]]
        self.assertIn("VERY_LOW_MAX_SIMILARITY", codes)

    def test_near_one_acceleration_warns(self):
        r = _make_pipeline_result(accel=1.0)
        result = self.a.detect_anomalies(r)
        codes = [a["code"] for a in result["anomalies"]]
        self.assertIn("NEAR_ZERO_ACCELERATION", codes)

    def test_extreme_acceleration_warns(self):
        r = _make_pipeline_result(accel=15.0)
        result = self.a.detect_anomalies(r)
        codes = [a["code"] for a in result["anomalies"]]
        self.assertIn("EXTREME_ACCELERATION", codes)

    def test_negative_sentiment_decrease_warns(self):
        r = _make_pipeline_result()
        r["sentiment"] = [
            {"date": "2025-02-13", "negative": 50.0, "neutral": 30.0, "positive": 20.0},
            {"date": "2025-02-14", "negative": 30.0, "neutral": 40.0, "positive": 30.0},
        ]
        result = self.a.detect_anomalies(r)
        codes = [a["code"] for a in result["anomalies"]]
        self.assertIn("NEGATIVE_SENTIMENT_DECREASED", codes)

    def test_returns_correct_agent_name(self):
        result = self.a.detect_anomalies(_make_pipeline_result())
        self.assertEqual(result["agent"], "anomaly_detector")

    def test_empty_topics_no_crash(self):
        r = _make_pipeline_result()
        r["topics"] = []
        result = self.a.detect_anomalies(r)
        self.assertIn("status", result)


# ═════════════════════════════════════════════════════════════
# 7. agents/repair_agent.py
# ═════════════════════════════════════════════════════════════

class TestRepairAgent(unittest.TestCase):

    def setUp(self):
        from agents import repair_agent, validator_agent, anomaly_agent
        self.r = repair_agent
        self.v = validator_agent
        self.a = anomaly_agent

    def _run(self, pipeline_result):
        val    = self.v.validate(pipeline_result)
        anomaly= self.a.detect_anomalies(pipeline_result)
        return self.r.suggest_repairs(val, anomaly)

    def test_clean_result_healthy(self):
        result = self._run(_make_pipeline_result())
        self.assertEqual(result["overall_assessment"], "healthy — proceed to brief generation")
        self.assertFalse(result["issue_detected"])
        self.assertFalse(result["repair_required"])

    def test_no_topics_triggers_rerun(self):
        r = _make_pipeline_result()
        r["topics"] = []
        result = self._run(r)
        actions = [s["action"] for s in result["suggestions"]]
        self.assertIn("rerun_topic_modeling", actions)

    def test_no_matches_triggers_news_fetch(self):
        r = _make_pipeline_result()
        r["news_matches"] = []
        result = self._run(r)
        actions = [s["action"] for s in result["suggestions"]]
        self.assertIn("rerun_news_fetch", actions)

    def test_no_duplicate_actions(self):
        r = _make_pipeline_result()
        r["topics"] = []
        result = self._run(r)
        actions = [s["action"] for s in result["suggestions"]]
        self.assertEqual(len(actions), len(set(actions)))

    def test_repair_required_on_failure(self):
        r = _make_pipeline_result()
        r["topics"] = []
        r["news_matches"] = []
        result = self._run(r)
        self.assertTrue(result["repair_required"])

    def test_suggestions_have_required_keys(self):
        r = _make_pipeline_result()
        r["topics"] = []
        result = self._run(r)
        for s in result["suggestions"]:
            self.assertIn("action", s)
            self.assertIn("params", s)
            self.assertIn("reason", s)

    def test_returns_correct_agent_name(self):
        result = self._run(_make_pipeline_result())
        self.assertEqual(result["agent"], "repair")

    def test_repair_map_covers_common_codes(self):
        from agents.repair_agent import REPAIR_MAP
        expected_codes = [
            "NO_TOPICS", "SINGLE_TOPIC", "DOMINANT_TOPIC",
            "NO_MATCHES", "LOW_NEWS_COUNT", "ALL_LOW_SIMILARITY",
            "VERY_LOW_MAX_SIMILARITY", "NO_SENTIMENT", "NO_ACCELERATION",
        ]
        for code in expected_codes:
            self.assertIn(code, REPAIR_MAP, f"{code} missing from REPAIR_MAP")


# ═════════════════════════════════════════════════════════════
# 8. agents/report_agent.py
# ═════════════════════════════════════════════════════════════

class TestReportAgent(unittest.TestCase):

    def _make_agent_results(self, v_status="pass", a_status="pass", suggestions=None):
        val    = {"status": v_status, "issues": [], "passed": v_status == "pass"}
        anomaly= {"status": a_status, "anomalies": [], "clean": a_status == "pass"}
        repair = {
            "agent"             : "repair",
            "issue_detected"    : bool(suggestions),
            "repair_required"   : v_status == "fail" or a_status == "fail",
            "overall_assessment": "healthy — proceed to brief generation",
            "suggestions"       : suggestions or [],
        }
        return val, anomaly, repair

    @pytest.mark.asyncio
    async def test_all_pass_produces_high_confidence(self):
        from agents import report_agent
        val, anomaly, repair = self._make_agent_results()
        with patch("agents.report_agent.db.save_diagnostic", new_callable=AsyncMock):
            report = await report_agent.generate_report("job-1", val, anomaly, repair)
        self.assertGreaterEqual(report["confidence_score"], 0.8)
        self.assertTrue(report["production_ready"])

    @pytest.mark.asyncio
    async def test_fail_status_lowers_confidence(self):
        from agents import report_agent
        val, anomaly, repair = self._make_agent_results(v_status="fail")
        with patch("agents.report_agent.db.save_diagnostic", new_callable=AsyncMock):
            report = await report_agent.generate_report("job-1", val, anomaly, repair)
        self.assertFalse(report["production_ready"])
        self.assertLess(report["confidence_score"], 0.5)

    @pytest.mark.asyncio
    async def test_report_contains_required_keys(self):
        from agents import report_agent
        val, anomaly, repair = self._make_agent_results()
        with patch("agents.report_agent.db.save_diagnostic", new_callable=AsyncMock):
            report = await report_agent.generate_report("job-1", val, anomaly, repair)
        for key in ["confidence_score", "production_ready", "validation_status",
                    "anomaly_status", "issues", "anomalies"]:
            self.assertIn(key, report)

    @pytest.mark.asyncio
    async def test_saves_four_diagnostics(self):
        from agents import report_agent
        val, anomaly, repair = self._make_agent_results()
        mock_save = AsyncMock()
        with patch("agents.report_agent.db.save_diagnostic", mock_save):
            await report_agent.generate_report("job-1", val, anomaly, repair)
        self.assertEqual(mock_save.call_count, 4)

    @pytest.mark.asyncio
    async def test_confidence_bounded_0_to_1(self):
        from agents import report_agent
        val, anomaly, repair = self._make_agent_results(v_status="fail", a_status="fail")
        with patch("agents.report_agent.db.save_diagnostic", new_callable=AsyncMock):
            report = await report_agent.generate_report("job-1", val, anomaly, repair)
        self.assertGreaterEqual(report["confidence_score"], 0.0)
        self.assertLessEqual(report["confidence_score"], 1.0)


# ═════════════════════════════════════════════════════════════
# 9. agents/supervisor.py
# ═════════════════════════════════════════════════════════════

class TestSupervisor(unittest.TestCase):

    @pytest.mark.asyncio
    async def test_run_direct_returns_dict(self):
        from agents import supervisor
        pr = _make_pipeline_result()
        mock_save = AsyncMock()
        with patch("agents.report_agent.db.save_diagnostic", mock_save):
            result = await supervisor._run_direct("job-1", pr)
        self.assertIn("validation", result)
        self.assertIn("anomaly", result)
        self.assertIn("repair", result)
        self.assertIn("report", result)

    @pytest.mark.asyncio
    async def test_run_supervisor_falls_back_when_crewai_absent(self):
        """Supervisor should use direct mode if crewai isn't installed."""
        from agents import supervisor
        original = supervisor.CREWAI_AVAILABLE
        supervisor.CREWAI_AVAILABLE = False
        pr = _make_pipeline_result()
        mock_save = AsyncMock()
        try:
            with patch("agents.report_agent.db.save_diagnostic", mock_save):
                result = await supervisor.run_supervisor("job-1", pr)
            self.assertIn("validation", result)
        finally:
            supervisor.CREWAI_AVAILABLE = original


# ═════════════════════════════════════════════════════════════
# 10. media_ecosystem.py  (mocked DB)
# ═════════════════════════════════════════════════════════════

class TestMediaEcosystem(unittest.TestCase):

    def _make_flow_rows(self):
        return [
            MagicMock(**{"__getitem__.side_effect": lambda k: {"subreddit": "Anarchism", "domain": "blackrosefed.org", "post_count": 11}[k]}),
        ]

    @pytest.mark.asyncio
    async def test_get_echo_scores_returns_sorted_list(self):
        import media_ecosystem as me
        mock_rows = [
            {"subreddit": "Anarchism", "echo_score": 26.7},
            {"subreddit": "socialism", "echo_score": 16.1},
            {"subreddit": "politics",  "echo_score": 4.3},
        ]
        async def fake_fetch(q):
            return mock_rows
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__  = AsyncMock(return_value=False)
        mock_conn.fetch = fake_fetch

        with patch("media_ecosystem.db.conn", return_value=mock_conn):
            result = await me.get_echo_scores()

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["subreddit"], "Anarchism")

    def test_cosine_similarity_computation(self):
        import media_ecosystem as me
        a = {"x": 1, "y": 0}
        b = {"x": 0, "y": 1}
        self.assertAlmostEqual(me._cosine(a, b), 0.0, places=6)

        c = {"x": 1, "y": 1}
        d = {"x": 1, "y": 1}
        self.assertAlmostEqual(me._cosine(c, d), 1.0, places=6)

    def test_cosine_zero_vector(self):
        import media_ecosystem as me
        a = {"x": 0, "y": 0}
        b = {"x": 1, "y": 1}
        self.assertEqual(me._cosine(a, b), 0.0)

    @pytest.mark.asyncio
    async def test_get_category_breakdown_returns_sorted(self):
        import media_ecosystem as me
        mock_rows = [
            {"category": "Media / News", "total": 60},
            {"category": "Advocacy / Org", "total": 30},
            {"category": "Video", "total": 10},
        ]
        async def fake_fetch(q, sub):
            return mock_rows
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__  = AsyncMock(return_value=False)
        mock_conn.fetch = fake_fetch

        with patch("media_ecosystem.db.conn", return_value=mock_conn):
            result = await me.get_category_breakdown("Anarchism")

        self.assertEqual(result[0]["cat"], "Media / News")
        self.assertAlmostEqual(result[0]["pct"], 60.0, places=0)

    @pytest.mark.asyncio
    async def test_get_category_breakdown_empty_returns_empty(self):
        import media_ecosystem as me
        async def fake_fetch(q, sub):
            return []
        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__  = AsyncMock(return_value=False)
        mock_conn.fetch = fake_fetch

        with patch("media_ecosystem.db.conn", return_value=mock_conn):
            result = await me.get_category_breakdown("Unknown")
        self.assertEqual(result, [])


# ═════════════════════════════════════════════════════════════
# 11. news_fetcher.py
# ═════════════════════════════════════════════════════════════

class TestNewsFetcher(unittest.TestCase):

    @pytest.mark.asyncio
    async def test_fetch_uses_cache_when_populated(self):
        import news_fetcher
        cached = [
            {"headline": f"headline {i}", "source": "s", "url": "u",
             "embedding": _make_vec()}
            for i in range(10)
        ]
        with patch("news_fetcher.db.get_news_for_date", new_callable=AsyncMock, return_value=cached):
            result = await news_fetcher.fetch_and_store_news(date(2025, 2, 14))
        self.assertEqual(len(result), 10)

    @pytest.mark.asyncio
    async def test_deduplication_removes_duplicates(self):
        import news_fetcher
        import httpx

        dup_items = [{"headline": "same headline", "source": "s", "url": "u"}] * 5

        with patch("news_fetcher.db.get_news_for_date", new_callable=AsyncMock, return_value=[]):
            with patch("news_fetcher._fetch_newsapi",   new_callable=AsyncMock, return_value=dup_items):
                with patch("news_fetcher._fetch_newsdata",  new_callable=AsyncMock, return_value=[]):
                    with patch("news_fetcher._fetch_currents",  new_callable=AsyncMock, return_value=[]):
                        with patch("news_fetcher._fetch_wikipedia", new_callable=AsyncMock, return_value=[]):
                            with patch("news_fetcher.embed", return_value=[_make_vec()]):
                                with patch("news_fetcher.db.save_news_item", new_callable=AsyncMock):
                                    result = await news_fetcher.fetch_and_store_news(date(2025, 2, 14))
        self.assertEqual(len(result), 1)

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_headlines(self):
        import news_fetcher
        with patch("news_fetcher.db.get_news_for_date", new_callable=AsyncMock, return_value=[]):
            with patch("news_fetcher._fetch_newsapi",   new_callable=AsyncMock, return_value=[]):
                with patch("news_fetcher._fetch_newsdata",  new_callable=AsyncMock, return_value=[]):
                    with patch("news_fetcher._fetch_currents",  new_callable=AsyncMock, return_value=[]):
                        with patch("news_fetcher._fetch_wikipedia", new_callable=AsyncMock, return_value=[]):
                            result = await news_fetcher.fetch_and_store_news(date(2025, 2, 14))
        self.assertEqual(result, [])


# ═════════════════════════════════════════════════════════════
# 12. sentiment_engine.py — label mapper
# ═════════════════════════════════════════════════════════════

class TestSentimentEngine(unittest.TestCase):

    def test_label_map_keys(self):
        from sentiment_engine import LABEL_MAP
        self.assertIn("LABEL_0", LABEL_MAP)
        self.assertIn("LABEL_1", LABEL_MAP)
        self.assertIn("LABEL_2", LABEL_MAP)
        self.assertEqual(LABEL_MAP["LABEL_0"], "negative")
        self.assertEqual(LABEL_MAP["LABEL_1"], "neutral")
        self.assertEqual(LABEL_MAP["LABEL_2"], "positive")

    def test_classify_empty_returns_neutral(self):
        from sentiment_engine import _classify_batch
        result = _classify_batch([])
        self.assertEqual(result["neutral"], 100.0)
        self.assertEqual(result["negative"], 0.0)
        self.assertEqual(result["positive"], 0.0)

    def test_classify_sums_to_100(self):
        from sentiment_engine import _classify_batch
        mock_pipe_output = [
            [{"label": "LABEL_0", "score": 0.8}, {"label": "LABEL_1", "score": 0.1}, {"label": "LABEL_2", "score": 0.1}],
            [{"label": "LABEL_2", "score": 0.9}, {"label": "LABEL_0", "score": 0.05}, {"label": "LABEL_1", "score": 0.05}],
        ]
        with patch("sentiment_engine._get_pipeline") as mock_get:
            mock_get.return_value = MagicMock(return_value=mock_pipe_output)
            result = _classify_batch(["text 1", "text 2"])
        total = result["negative"] + result["neutral"] + result["positive"]
        self.assertAlmostEqual(total, 100.0, places=1)

    @pytest.mark.asyncio
    async def test_run_sentiment_skips_empty_dates(self):
        from sentiment_engine import run_sentiment_evolution
        with patch("sentiment_engine.db.get_texts_for_date", new_callable=AsyncMock, return_value=[]):
            result = await run_sentiment_evolution("job-1", date(2025, 2, 14))
        self.assertEqual(result, [])

    @pytest.mark.asyncio
    async def test_run_sentiment_stores_three_days(self):
        from sentiment_engine import run_sentiment_evolution
        fake_texts = ["some text about politics"] * 10
        fake_sentiment = {"negative": 30.0, "neutral": 40.0, "positive": 30.0}

        with patch("sentiment_engine.db.get_texts_for_date", new_callable=AsyncMock, return_value=fake_texts):
            with patch("sentiment_engine._classify_batch", return_value=fake_sentiment):
                with patch("sentiment_engine.db.save_sentiment", new_callable=AsyncMock):
                    result = await run_sentiment_evolution("job-1", date(2025, 2, 14))

        self.assertEqual(len(result), 3)
        dates = [r["date"] for r in result]
        self.assertIn("2025-02-13", dates)
        self.assertIn("2025-02-14", dates)
        self.assertIn("2025-02-15", dates)


# ═════════════════════════════════════════════════════════════
# 13. topic_engine.py
# ═════════════════════════════════════════════════════════════

class TestTopicEngine(unittest.TestCase):

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_posts(self):
        from topic_engine import run_topic_modeling
        with patch("topic_engine.db.get_posts_for_date", new_callable=AsyncMock, return_value=[]):
            result = await run_topic_modeling("job-1", date(2025, 2, 14))
        self.assertEqual(result, [])

    @pytest.mark.asyncio
    async def test_skips_noise_topic(self):
        from topic_engine import run_topic_modeling
        import numpy as np

        fake_rows = [{"title": f"title {i}", "embedding": str([0.1] * 384)} for i in range(10)]
        fake_topic_info = MagicMock()
        fake_topic_info.iterrows.return_value = [
            (0, {"Topic": -1, "Count": 3}),   # noise — should be skipped
            (1, {"Topic":  0, "Count": 7}),   # real topic
        ]

        mock_model = MagicMock()
        mock_model.fit_transform.return_value = ([-1]*3 + [0]*7, None)
        mock_model.get_topic_info.return_value = fake_topic_info
        mock_model.get_topic.return_value = [("word1", 0.9), ("word2", 0.8)]

        with patch("topic_engine.db.get_posts_for_date", new_callable=AsyncMock, return_value=fake_rows):
            with patch("topic_engine.db.save_topic", new_callable=AsyncMock):
                with patch("topic_engine.get_embedder", return_value=MagicMock()):
                    with patch("topic_engine.BERTopic", return_value=mock_model):
                        result = await run_topic_modeling("job-1", date(2025, 2, 14))

        topic_ids = [t["topic_id"] for t in result]
        self.assertNotIn(-1, topic_ids)


# ═════════════════════════════════════════════════════════════
# 14. llm_engine.py
# ═════════════════════════════════════════════════════════════

class TestLlmEngine(unittest.TestCase):

    @pytest.mark.asyncio
    async def test_generate_brief_calls_litellm_and_saves(self):
        from llm_engine import generate_brief

        mock_message = MagicMock()
        mock_message.content = "This is the catalyst brief text."
        
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("llm_engine.acompletion", new_callable=AsyncMock, return_value=mock_response):
            with patch("llm_engine.db.save_brief", new_callable=AsyncMock) as mock_save:
                result = await generate_brief(
                    job_id="job-1",
                    spike_date="2025-02-14",
                    acceleration={"baseline": 100, "spike": 350, "ratio": 3.5},
                    topics=[{"topic_id": 0, "size_percent": 60, "keywords": ["policy", "vote"],
                             "centroid": _make_vec()}],
                    matches=[{"topic_id": 0, "headline": "Election results", "source": "AP",
                              "url": "http://ap.com", "similarity": 0.82}],
                    sentiment=[{"date": "2025-02-14", "negative": 35, "neutral": 40, "positive": 25}],
                )

        self.assertEqual(result, "This is the catalyst brief text.")
        mock_save.assert_called_once_with("job-1", "This is the catalyst brief text.")

    @pytest.mark.asyncio
    async def test_prompt_contains_spike_date(self):
        from llm_engine import _build_prompt
        payload = {
            "spike_date"  : "2025-02-14",
            "acceleration": {"baseline": 100, "spike": 350, "ratio": 3.5},
            "topics"      : [{"topic_id": 0, "size_percent": 60, "keywords": ["test"],
                               "catalysts": [{"headline": "h", "similarity": 0.8, "source": "s"}]}],
            "sentiment"   : [],
        }
        prompt = _build_prompt(payload)
        self.assertIn("2025-02-14", prompt)
        self.assertIn("3.5", prompt)


# ═════════════════════════════════════════════════════════════
# 15. pipeline.py — structure checks
# ═════════════════════════════════════════════════════════════

class TestPipeline(unittest.TestCase):

    def test_module_imports(self):
        import pipeline
        self.assertTrue(callable(pipeline.run_spike_pipeline))

    @pytest.mark.asyncio
    async def test_pipeline_marks_failed_when_no_topics(self):
        import pipeline

        with patch("pipeline.reddit_ingest.enrich_for_spike", new_callable=AsyncMock, return_value={}):
            with patch("pipeline.topic_engine.run_topic_modeling", new_callable=AsyncMock, return_value=[]):
                with patch("pipeline.db.update_job_status", new_callable=AsyncMock) as mock_status:
                    await pipeline.run_spike_pipeline("job-1", date(2025, 2, 14))

        mock_status.assert_called_with("job-1", "failed", "No topics detected")

    @pytest.mark.asyncio
    async def test_pipeline_marks_done_on_success(self):
        import pipeline

        with patch("pipeline.reddit_ingest.enrich_for_spike", new_callable=AsyncMock, return_value={}):
            with patch("pipeline.topic_engine.run_topic_modeling", new_callable=AsyncMock,
                       return_value=[{"topic_id": 0, "centroid": _make_vec(), "size_percent": 100.0, "keywords": ["k"]}]):
                with patch("pipeline.news_fetcher.fetch_and_store_news", new_callable=AsyncMock,
                           return_value=[{"headline": "h", "source": "s", "url": "u", "embedding": _make_vec()}]):
                    with patch("pipeline.matcher.run_similarity_matching", new_callable=AsyncMock, return_value=[]):
                        with patch("pipeline.db.count_posts_for_date", new_callable=AsyncMock, return_value=100):
                            with patch("pipeline.db.save_spike_metrics", new_callable=AsyncMock):
                                with patch("pipeline.sentiment_engine.run_sentiment_evolution",
                                           new_callable=AsyncMock, return_value=[]):
                                    with patch("pipeline.run_supervisor", new_callable=AsyncMock,
                                               return_value={"report": {"confidence_score": 0.9}}):
                                        with patch("pipeline.llm_engine.generate_brief", new_callable=AsyncMock):
                                            with patch("pipeline.db.update_job_status", new_callable=AsyncMock) as mock_status:
                                                await pipeline.run_spike_pipeline("job-1", date(2025, 2, 14))

        # Last call should be "done"
        final_call = mock_status.call_args_list[-1]
        self.assertEqual(final_call[0][1], "done")


# ═════════════════════════════════════════════════════════════
# 16. ingest.py — parse helpers
# ═════════════════════════════════════════════════════════════

class TestIngest(unittest.TestCase):

    def test_parse_ts_standard_format(self):
        from ingest import parse_ts
        result = parse_ts("2025-02-14 10:30:00")
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 2)
        self.assertEqual(result.day, 14)

    def test_parse_ts_iso_format(self):
        from ingest import parse_ts
        result = parse_ts("2025-02-14T10:30:00")
        self.assertIsInstance(result, datetime)

    def test_parse_ts_date_only(self):
        from ingest import parse_ts
        result = parse_ts("2025-02-14")
        self.assertIsInstance(result, datetime)

    def test_parse_ts_invalid_raises(self):
        from ingest import parse_ts
        with self.assertRaises(ValueError):
            parse_ts("not-a-date")

    def test_parse_ts_whitespace_handled(self):
        from ingest import parse_ts
        result = parse_ts("  2025-02-14  ")
        self.assertIsInstance(result, datetime)


# ═════════════════════════════════════════════════════════════
# 17. main.py — FastAPI routes (TestClient)
# ═════════════════════════════════════════════════════════════

class TestMainRoutes(unittest.TestCase):

    def setUp(self):
        # Mock DB pool so startup doesn't connect to real Neon
        self.db_patch = patch("db.init_pool", new_callable=AsyncMock)
        self.db_patch.start()
        self.close_patch = patch("db.close_pool", new_callable=AsyncMock)
        self.close_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.close_patch.stop()

    def _get_client(self):
        from fastapi.testclient import TestClient
        import main
        return TestClient(main.app)

    def test_health_endpoint(self):
        with patch("db.init_pool", new_callable=AsyncMock):
            client = self._get_client()
            resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("modules", data)

    def test_analyze_spike_returns_job_id(self):
        mock_job_id = "550e8400-e29b-41d4-a716-446655440000"
        with patch("db.init_pool", new_callable=AsyncMock):
            with patch("db.create_spike_job", new_callable=AsyncMock, return_value=mock_job_id):
                with patch("pipeline.run_spike_pipeline", new_callable=AsyncMock):
                    client = self._get_client()
                    resp = client.post(
                        "/analyze-spike",
                        json={"spike_date": "2025-02-14"}
                    )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["status"], "processing")
        self.assertIn("poll_url", data)

    def test_job_status_404_for_unknown(self):
        with patch("db.init_pool", new_callable=AsyncMock):
            with patch("db.get_job", new_callable=AsyncMock, return_value=None):
                client = self._get_client()
                resp = client.get("/job-status/nonexistent-uuid")
        self.assertEqual(resp.status_code, 404)

    def test_job_status_processing(self):
        mock_job = {"status": "processing", "job_id": "test-uuid",
                    "spike_date": date(2025, 2, 14), "error_msg": None}
        with patch("db.init_pool", new_callable=AsyncMock):
            with patch("db.get_job", new_callable=AsyncMock, return_value=mock_job):
                client = self._get_client()
                resp = client.get("/job-status/test-uuid")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "processing")

    def test_volume_endpoint_returns_list(self):
        with patch("db.init_pool", new_callable=AsyncMock):
            with patch("db.get_volume_series", new_callable=AsyncMock, return_value=[]):
                client = self._get_client()
                resp = client.get("/volume")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("volume", resp.json())

    def test_subreddits_endpoint(self):
        with patch("db.init_pool", new_callable=AsyncMock):
            with patch("media_ecosystem.get_all_subreddits", new_callable=AsyncMock,
                       return_value=["Anarchism", "Conservative"]):
                client = self._get_client()
                resp = client.get("/subreddits")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("subreddits", resp.json())

    def test_echo_scores_endpoint(self):
        mock_scores = [{"subreddit": "Anarchism", "lift": 26.7}]
        with patch("db.init_pool", new_callable=AsyncMock):
            with patch("media_ecosystem.get_echo_scores", new_callable=AsyncMock,
                       return_value=mock_scores):
                client = self._get_client()
                resp = client.get("/echo-scores")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("scores", resp.json())

    def test_category_breakdown_404_unknown_subreddit(self):
        with patch("db.init_pool", new_callable=AsyncMock):
            with patch("media_ecosystem.get_category_breakdown", new_callable=AsyncMock, return_value=[]):
                client = self._get_client()
                resp = client.get("/category-breakdown/FakeSub")
        self.assertEqual(resp.status_code, 404)

    def test_top_domains_404_unknown_subreddit(self):
        with patch("db.init_pool", new_callable=AsyncMock):
            with patch("media_ecosystem.get_top_domains", new_callable=AsyncMock, return_value=[]):
                client = self._get_client()
                resp = client.get("/top-domains/FakeSub")
        self.assertEqual(resp.status_code, 404)


# ═════════════════════════════════════════════════════════════
# 18. reddit_ingest.py — structure checks
# ═════════════════════════════════════════════════════════════

class TestRedditIngest(unittest.TestCase):

    def test_module_imports(self):
        import reddit_ingest
        self.assertTrue(callable(reddit_ingest.enrich_for_spike))

    @pytest.mark.asyncio
    async def test_returns_warning_when_no_subreddits(self):
        import reddit_ingest
        with patch("reddit_ingest.db.count_posts_for_date", new_callable=AsyncMock, return_value=0):
            with patch("reddit_ingest._get_subreddits_from_db", new_callable=AsyncMock, return_value=[]):
                with patch("reddit_ingest._get_reddit", return_value=MagicMock()):
                    result = await reddit_ingest.enrich_for_spike(date(2025, 2, 14))
        self.assertIn("warning", result)

    def test_timestamp_filter_logic(self):
        from reddit_ingest import _ts_in_range
        from datetime import datetime, timedelta
        base = datetime(2025, 2, 14, 12, 0, 0)
        start = datetime(2025, 2, 14, 0, 0, 0)
        end   = datetime(2025, 2, 15, 0, 0, 0)
        self.assertTrue(_ts_in_range(base.timestamp(), start, end))
        self.assertFalse(_ts_in_range((start - timedelta(hours=1)).timestamp(), start, end))
        self.assertFalse(_ts_in_range(end.timestamp(), start, end))


# ═════════════════════════════════════════════════════════════
# 19. agents/__init__.py
# ═════════════════════════════════════════════════════════════

class TestAgentsPackage(unittest.TestCase):

    def test_package_importable(self):
        import agents
        self.assertIsNotNone(agents)

    def test_all_agent_modules_importable(self):
        from agents import validator_agent, anomaly_agent, repair_agent, report_agent, supervisor
        for m in [validator_agent, anomaly_agent, repair_agent, report_agent, supervisor]:
            self.assertIsNotNone(m)

    def test_each_agent_has_expected_entry_point(self):
        from agents import validator_agent, anomaly_agent, repair_agent
        self.assertTrue(callable(validator_agent.validate))
        self.assertTrue(callable(anomaly_agent.detect_anomalies))
        self.assertTrue(callable(repair_agent.suggest_repairs))


# ═════════════════════════════════════════════════════════════
# RUN
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
