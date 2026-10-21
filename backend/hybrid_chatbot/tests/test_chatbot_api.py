"""HTTP surface of the mounted chatbot app (no network, fake LLM, tmp DB)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import FakeLLM, make_pipeline
from hybrid_chatbot import api

ECHO_QUESTION = "Which subreddit has the highest echo-chamber lift in the dataset?"


@pytest.fixture
def client(built_db, monkeypatch):
    llm = FakeLLM()
    pipeline = make_pipeline(llm, built_db)
    monkeypatch.setattr(api, "pipeline", pipeline)
    yield TestClient(api.app), llm, pipeline
    pipeline.sql_store.close()


def test_query_without_debug_keeps_provenance(client):
    http, llm, _ = client
    resp = http.post("/query", json={"query": ECHO_QUESTION, "debug": False})
    assert resp.status_code == 200
    body = resp.json()

    # Backward-compatible keys.
    assert "answer" in body and "sql" in body
    assert body["sql"]["rows"][0]["subreddit"] == "Anarchism"
    # Provenance survives debug=false.
    assert body["answer_mode"] == "deterministic_sql"
    assert body["llm_used"] is False
    assert body["dataset"]["date_range"] == {"start": "2024-07-23", "end": "2025-02-18"}
    assert body["dataset"]["snapshot"] == "historical"
    assert body["evidence"] and body["evidence"][0]["type"] == "sql"
    assert body["retrieval"]["method"] == "lexical_token_overlap"
    # Raw internals are stripped.
    for key in ("route", "timing", "dataset_chunks", "web_articles", "debug"):
        assert key not in body
    assert llm.calls == []


def test_query_with_debug_adds_internals(client):
    http, _, _ = client
    body = http.post("/query", json={"query": ECHO_QUESTION, "debug": True}).json()
    assert body["route"] == "chat_sql_direct"
    assert "timing" in body and "dataset_chunks" in body and "debug" in body
    assert body["dataset_chunks"][0]["row_key"]


def test_unavailable_state_is_json_serialisable(csv_dir_without, tmp_path, monkeypatch):
    llm = FakeLLM()
    pipeline = make_pipeline(llm, tmp_path / "x.duckdb", data_dir=csv_dir_without("echo_chamber_scores.csv"))
    monkeypatch.setattr(api, "pipeline", pipeline)
    body = TestClient(api.app).post("/query", json={"query": ECHO_QUESTION}).json()
    assert body["answer_mode"] == "sql_unavailable"
    assert body["sql"]["status"] == "unavailable"
    health = TestClient(api.app).get("/health").json()
    assert health["sql"]["state"] == "degraded"
    assert health["sql"]["missing_tables"] == ["echo_chamber_scores"]
    pipeline.sql_store.close()


def test_health_reports_sql_status_and_date_range(client):
    http, _, _ = client
    body = http.get("/health").json()
    assert body["status"] == "ok"
    assert body["sql"]["state"] == "ready"
    assert len(body["sql"]["available_tables"]) == 12
    assert body["sql"]["missing_tables"] == []
    assert body["dataset_date_range"] == {"start": "2024-07-23", "end": "2025-02-18"}
    assert "llm_ready" in body and "web_search_ready" in body


def test_init_resources_initializes_sql_store(client):
    _, _, pipeline = client
    assert pipeline.sql_store.status.state == "uninitialized"
    status = api.init_resources()
    assert status["state"] == "ready"
    assert pipeline.sql_store.status.state == "ready"
    assert api.init_resources()["state"] == "ready"  # idempotent


def test_init_resources_records_failure_instead_of_raising(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    pipeline = make_pipeline(FakeLLM(), tmp_path / "n.duckdb", data_dir=empty)
    monkeypatch.setattr(api, "pipeline", pipeline)
    status = api.init_resources()
    assert status["state"] == "unavailable" and status["error"]
    assert TestClient(api.app).get("/health").json()["sql"]["state"] == "unavailable"


def test_health_status_is_degraded_when_a_table_is_missing(csv_dir_without, tmp_path, monkeypatch):
    pipeline = make_pipeline(FakeLLM(), tmp_path / "x.duckdb", data_dir=csv_dir_without("echo_chamber_scores.csv"))
    monkeypatch.setattr(api, "pipeline", pipeline)
    resp = TestClient(api.app).get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["sql"]["state"] == "degraded" and body["sql"]["missing_tables"] == ["echo_chamber_scores"]
    for key in ("llm_ready", "web_search_ready", "sql", "dataset_date_range"):
        assert key in body
    pipeline.sql_store.close()


def test_health_status_is_unavailable_when_no_table_can_be_served(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    pipeline = make_pipeline(FakeLLM(), tmp_path / "n.duckdb", data_dir=empty)
    monkeypatch.setattr(api, "pipeline", pipeline)
    resp = TestClient(api.app).get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["sql"]["state"] == "unavailable" and body["sql"]["available_tables"] == []
    for key in ("llm_ready", "web_search_ready", "sql", "dataset_date_range"):
        assert key in body
    pipeline.sql_store.close()
