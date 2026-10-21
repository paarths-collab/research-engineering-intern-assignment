"""
Tests — mock/sample data labelling on the Globe events routes.

When the pipeline has produced no output the events routes fall back to the
built-in ``_MOCK_EVENTS``. Every response that can be built from that payload
must say so (``data_source == "mock_sample"``, ``is_mock is True``); responses
built from a real ``global_events_*.json`` must say ``is_mock is False`` and
carry the file's own ``generated_at``.

The app is assembled like tests/test_api.py (routers on a bare FastAPI app, no
lifespan => no DuckDB). The pipeline output directory is redirected to a tmp dir
and every network / LLM / DB / cache-file touchpoint is stubbed.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import events as events_routes

PIPELINE_GENERATED_AT = "2026-01-02T03:04:05+00:00"
REAL_EVENT_ID = "11111111-2222-3333-4444-555555555555"
MOCK_EVENT_ID = "mock-tehran"


def _real_payload() -> dict:
    return {
        "run_id": "abc12345",
        "generated_at": PIPELINE_GENERATED_AT,
        "event_count": 1,
        "events": [
            {
                "id": REAL_EVENT_ID,
                "title": "Fixture City — Escalating",
                "locations": [{"name": "Fixture City", "lat": 10.0, "lon": 20.0}],
                "impact_score": 0.6,
                "sentiment": "negative",
                "risk_level": "High",
                "confidence": "High",
                "summary": "Fixture summary.",
                "strategic_implications": ["Fixture implication"],
                "reddit_metrics": {"post_count": 1, "subreddits": ["worldnews"]},
                "news_sources": [
                    {"title": "Fixture headline", "url": "https://example.com/a", "source": "Example"}
                ],
                "last_updated": PIPELINE_GENERATED_AT,
            }
        ],
    }


def build_globe_app() -> FastAPI:
    from app.api.routes import health, pipeline

    app = FastAPI(title="Globe API (labelling test)")
    app.include_router(health.router)
    app.include_router(events_routes.router)
    app.include_router(pipeline.router)
    return app


@pytest.fixture
def client():
    return TestClient(build_globe_app())


@pytest.fixture
def isolated(monkeypatch):
    """Stub every side-effect the events routes could have (network, LLM, DB, cache file)."""
    monkeypatch.setattr(events_routes, "settings", SimpleNamespace(GROQ_API_KEY="test-key"))
    monkeypatch.setattr(
        events_routes, "request_chat_completion", AsyncMock(return_value="stub report")
    )
    for name in ("_search_tavily", "_search_newsapi", "_search_gnews", "_search_newsdata"):
        monkeypatch.setattr(events_routes, name, AsyncMock(return_value=[]))

    class _FakeResponse:
        status_code = 404
        content = b""

        def json(self):
            return {}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *args, **kwargs):
            return _FakeResponse()

    monkeypatch.setattr(events_routes.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(events_routes, "_load_analysis_cache", lambda: {})
    monkeypatch.setattr(events_routes, "_save_analysis_cache", lambda cache: None)
    monkeypatch.setattr(
        events_routes,
        "_fetch_reddit_context_from_db",
        lambda event, max_posts=50: {
            "top_posts": [], "top_comments": [], "related_subreddits": [], "reddit_post_ids": [],
        },
    )


@pytest.fixture
def no_output_dir(tmp_path, monkeypatch, isolated):
    """The real loader pointed at an empty directory: no pipeline output exists."""
    monkeypatch.setattr(
        "app.pipeline.orchestrator.get_settings", lambda: SimpleNamespace(DATA_DIR=str(tmp_path))
    )
    return tmp_path


@pytest.fixture
def output_dir(tmp_path, monkeypatch, isolated):
    """The real loader pointed at a directory holding a tiny pipeline output file."""
    (tmp_path / "global_events_2026-01-02.json").write_text(
        json.dumps(_real_payload()), encoding="utf-8"
    )
    monkeypatch.setattr(
        "app.pipeline.orchestrator.get_settings", lambda: SimpleNamespace(DATA_DIR=str(tmp_path))
    )
    return tmp_path


def assert_mock(body: dict):
    assert body["is_mock"] is True
    assert body["data_source"] == "mock_sample"
    assert body["data_generated_at"] is None
    assert "sample" in body["data_notice"].lower()


def assert_real(body: dict):
    assert body["is_mock"] is False
    assert body["data_source"] == "pipeline_output"
    assert body["data_generated_at"] == PIPELINE_GENERATED_AT
    assert "data_notice" not in body


class TestNoPipelineOutput:
    def test_events_list_is_labelled_mock(self, client, no_output_dir):
        body = client.get("/events/").json()
        assert body["total"] == len(events_routes._MOCK_EVENTS) > 0
        assert_mock(body)

    def test_summary_is_labelled_mock(self, client, no_output_dir):
        body = client.get("/events/summary").json()
        assert body["total_events"] > 0
        assert_mock(body)

    def test_map_is_labelled_mock(self, client, no_output_dir):
        body = client.get("/events/map").json()
        assert body["pin_count"] > 0
        assert_mock(body)

    def test_event_detail_is_labelled_mock(self, client, no_output_dir):
        body = client.get(f"/events/{MOCK_EVENT_ID}").json()
        assert body["id"] == MOCK_EVENT_ID
        assert_mock(body)
        # Labels must not leak into the shared module-level mock list.
        assert all("is_mock" not in e for e in events_routes._MOCK_EVENTS)

    def test_unknown_event_is_still_404(self, client, no_output_dir):
        assert client.get("/events/does-not-exist").status_code == 404

    def test_global_ai_analysis_is_labelled_mock(self, client, no_output_dir):
        body = client.post("/events/ai-analysis").json()
        assert body["report"] == "stub report"
        assert_mock(body)

    def test_event_ai_analysis_is_labelled_mock(self, client, no_output_dir):
        body = client.post(f"/events/{MOCK_EVENT_ID}/ai-analysis").json()
        assert body["report"] == "stub report"
        assert_mock(body)

    def test_news_analysis_is_labelled_mock(self, client, no_output_dir):
        body = client.post(f"/events/{MOCK_EVENT_ID}/news-analysis").json()
        assert body["event_id"] == MOCK_EVENT_ID
        assert_mock(body)

    def test_news_analysis_template_topics_are_marked(self, client, no_output_dir, monkeypatch):
        monkeypatch.setattr(events_routes, "settings", SimpleNamespace(GROQ_API_KEY=""))
        body = client.post(f"/events/{MOCK_EVENT_ID}/news-analysis").json()
        assert body["topic_sentences_source"] == "template_fallback"
        assert_mock(body)

    def test_news_analysis_llm_topics_are_marked(self, client, no_output_dir):
        body = client.post(f"/events/{MOCK_EVENT_ID}/news-analysis").json()
        assert body["topic_sentences_source"] == "groq_llm"

    def test_event_analyze_is_labelled_mock(self, client, no_output_dir):
        body = client.post(f"/events/{MOCK_EVENT_ID}/analyze").json()
        assert body["analysis_report"] == "stub report"
        assert_mock(body)

    def test_location_news_fallback_to_mock_pipeline_news_is_labelled(self, client, no_output_dir):
        # Reverse geocoding (stubbed 404) and every news search return nothing, so the
        # route consults the stored payload for the place name => mock data was used.
        body = client.post("/events/news", json={"latitude": 35.69, "longitude": 51.39}).json()
        assert_mock(body)


class TestWithPipelineOutput:
    def test_events_list_is_labelled_real(self, client, output_dir):
        body = client.get("/events/").json()
        assert body["total"] == 1
        assert body["events"][0]["id"] == REAL_EVENT_ID
        assert_real(body)

    def test_summary_is_labelled_real(self, client, output_dir):
        body = client.get("/events/summary").json()
        assert body["run_id"] == "abc12345"
        assert_real(body)

    def test_map_is_labelled_real(self, client, output_dir):
        body = client.get("/events/map").json()
        assert body["pin_count"] == 1
        assert_real(body)

    def test_event_detail_is_labelled_real(self, client, output_dir):
        body = client.get(f"/events/{REAL_EVENT_ID}").json()
        assert body["title"] == "Fixture City — Escalating"
        assert_real(body)

    def test_mock_event_not_served_when_real_output_exists(self, client, output_dir):
        assert client.get(f"/events/{MOCK_EVENT_ID}").status_code == 404

    def test_global_ai_analysis_is_labelled_real(self, client, output_dir):
        assert_real(client.post("/events/ai-analysis").json())

    def test_event_ai_analysis_is_labelled_real(self, client, output_dir):
        assert_real(client.post(f"/events/{REAL_EVENT_ID}/ai-analysis").json())

    def test_news_analysis_is_labelled_real(self, client, output_dir):
        body = client.post(f"/events/{REAL_EVENT_ID}/news-analysis").json()
        assert_real(body)
        assert any(a["via"] == "pipeline" for a in body["articles"])

    def test_event_analyze_is_labelled_real(self, client, output_dir):
        assert_real(client.post(f"/events/{REAL_EVENT_ID}/analyze").json())

    def test_location_news_pipeline_fallback_is_labelled_real(self, client, output_dir):
        body = client.post("/events/news", json={"latitude": 10.0, "longitude": 20.0}).json()
        assert_real(body)
        assert body["articles"][0]["title"] == "Fixture headline"


class TestLabelHelpers:
    def test_empty_payload_from_loader_falls_back_to_mock(self, client, monkeypatch):
        monkeypatch.setattr(events_routes, "load_latest_output", lambda: {})
        assert_mock(client.get("/events/").json())

    def test_existing_payload_keys_are_unchanged(self, client, output_dir):
        body = client.get("/events/").json()
        assert {"generated_at", "total", "events"} <= set(body)
        assert body["generated_at"] == PIPELINE_GENERATED_AT
