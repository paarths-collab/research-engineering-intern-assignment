"""Pipeline behaviour: provenance, answer modes, unavailable SQL, date anchoring."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import pytest

from conftest import REPO_DATA_DIR, FakeLLM, FakeWeb

ECHO_QUESTION = "Which subreddit has the highest echo-chamber lift in the dataset?"
SYNTHESIS_QUESTION = "Explain the narrative about Trump birthright citizenship from salon.com"
OUT_OF_DATASET_QUESTION = "What is the best recipe for chocolate cake?"


def _echo_max_row() -> tuple[str, float]:
    df = pd.read_csv(REPO_DATA_DIR / "echo_chamber_scores.csv")
    row = df.sort_values("lift", ascending=False).iloc[0]
    return str(row["subreddit"]), float(row["lift"])


def test_echo_question_is_still_a_suggested_example():
    page = REPO_DATA_DIR.parent / "frontend" / "app" / "chatbot" / "page.jsx"
    if not page.exists():
        pytest.skip("frontend not present")
    assert ECHO_QUESTION in page.read_text(encoding="utf-8")


def test_historical_question_is_deterministic_sql_with_provenance(built_db, fake_llm, pipeline_factory):
    subreddit, max_lift = _echo_max_row()
    assert max_lift == 26.704058011434945

    pipeline = pipeline_factory(fake_llm, built_db)
    result = pipeline.run(ECHO_QUESTION)

    assert fake_llm.calls == []
    assert result["answer_mode"] == "deterministic_sql"
    assert result["llm_used"] is False
    assert subreddit in result["answer"]
    assert f"{max_lift:.6f}" in result["answer"]

    sql_items = [e for e in result["evidence"] if e["type"] == "sql"]
    assert len(sql_items) == 1
    assert sql_items[0]["tables"] == ["echo_chamber_scores"]
    assert "echo_chamber_scores" in sql_items[0]["query"]
    assert sql_items[0]["rows"] == [{"subreddit": subreddit, "lift": max_lift}]

    assert result["dataset"]["date_range"] == {"start": "2024-07-23", "end": "2025-02-18"}
    assert result["dataset"]["snapshot"] == "historical"
    assert result["dataset"]["tables_used"] == ["echo_chamber_scores"]
    assert result["retrieval"]["method"] == "lexical_token_overlap"
    assert result["retrieval"]["sql"] == "keyword_template"
    assert result["sql"]["status"] == "ok"
    assert result["route"] == "chat_sql_direct"

    # Reproducible: same question, identical answer and evidence.
    again = pipeline.run(ECHO_QUESTION)
    assert again["answer"] == result["answer"]
    assert json.dumps(again["evidence"], sort_keys=True) == json.dumps(result["evidence"], sort_keys=True)
    assert again["dataset"] == result["dataset"]
    assert fake_llm.calls == []


def test_synthesis_question_calls_llm_once_with_snippets(built_db, fake_llm, pipeline_factory):
    pipeline = pipeline_factory(fake_llm, built_db)
    result = pipeline.run(SYNTHESIS_QUESTION)

    assert result["answer_mode"] == "llm_synthesis"
    assert result["llm_used"] is True
    assert result["answer"] == fake_llm.reply
    assert len(fake_llm.calls) == 1

    snippets = [e for e in result["evidence"] if e["type"] == "dataset_snippet"]
    assert snippets, "expected lexical snippets as evidence"
    prompt = fake_llm.calls[0]["user"]
    for item in snippets:
        assert item["text"] in prompt
        assert item["table"] and item["row_key"] and item["row_index"] >= 0
        assert isinstance(item["score"], float)
    dated = [s for s in snippets if s["table"] in ("narrative_registry", "narrative_intelligence_summary")]
    assert dated and all(s["date"] and len(s["date"]) == 10 for s in dated)
    assert result["dataset"]["tables_used"]
    assert set(result["dataset"]["tables_used"]) >= {s["table"] for s in snippets}
    assert result["route"] == "chat_dataset"


def test_snippet_row_keys_match_the_csv(built_db, fake_llm, pipeline_factory):
    pipeline = pipeline_factory(fake_llm, built_db)
    hits = pipeline.dataset_store.search("Daily volume posts 2025-01-20", top_k=20)
    daily = [h for h in hits if h["source"] == "daily_volume_v2"]
    assert daily
    csv = pd.read_csv(REPO_DATA_DIR / "daily_volume_v2.csv")
    for h in daily:
        row = csv.iloc[h["row_index"]]
        assert h["row_key"] == row["created_datetime"] == h["date"]
        assert str(int(row["post_count"])) in h["text"]


def test_llm_failure_falls_back_with_evidence(built_db, pipeline_factory):
    llm = FakeLLM(raises=RuntimeError("boom"))
    result = pipeline_factory(llm, built_db).run(SYNTHESIS_QUESTION)

    assert len(llm.calls) == 1
    assert result["answer_mode"] == "fallback_template"
    assert result["llm_used"] is False
    assert "could not reach the language model" in result["answer"]
    assert any(e["type"] == "dataset_snippet" and e["table"] and e["row_key"] for e in result["evidence"])


def test_out_of_dataset_question_is_refused_without_llm(built_db, fake_llm, pipeline_factory):
    result = pipeline_factory(fake_llm, built_db).run(OUT_OF_DATASET_QUESTION)

    assert fake_llm.calls == []
    assert result["answer_mode"] == "out_of_dataset"
    assert result["llm_used"] is False
    assert result["route"] == "chat_out_of_dataset"
    assert "does not appear to be answerable" in result["answer"]
    assert result["evidence"] == []
    assert result["dataset"]["tables_used"] == []
    assert result["dataset"]["date_range"]["end"] == "2025-02-18"


def test_missing_table_gives_explicit_unavailable_state(csv_dir_without, tmp_path, fake_llm, pipeline_factory):
    csv_dir = csv_dir_without("echo_chamber_scores.csv")
    pipeline = pipeline_factory(fake_llm, tmp_path / "g.duckdb", data_dir=csv_dir)
    result = pipeline.run(ECHO_QUESTION)

    assert pipeline.sql_store.status.state == "degraded"
    assert pipeline.sql_store.status.missing_tables == ["echo_chamber_scores"]
    assert result["answer_mode"] == "sql_unavailable"
    assert result["llm_used"] is False and fake_llm.calls == []
    assert result["sql"]["status"] == "unavailable"
    assert "echo_chamber_scores" in result["sql"]["error"]
    assert result["sql"]["missing_tables"] == ["echo_chamber_scores"]
    assert result["sql"]["rows"] == []
    assert "unavailable" in result["answer"].lower()
    assert "echo_chamber_scores" in result["answer"]
    assert "26.7" not in result["answer"] and "Anarchism" not in result["answer"]
    assert result["evidence"] == []


def test_other_questions_still_work_when_one_table_is_missing(csv_dir_without, tmp_path, fake_llm, pipeline_factory):
    csv_dir = csv_dir_without("echo_chamber_scores.csv")
    pipeline = pipeline_factory(fake_llm, tmp_path / "g2.duckdb", data_dir=csv_dir)
    result = pipeline.run("What are the top domains by frequency across subreddit_domain_flow_v2?")
    assert result["sql"]["status"] == "ok"
    assert result["sql"]["rows"]
    assert result["answer_mode"] == "llm_synthesis"


def test_all_data_unavailable_is_reported_not_faked(tmp_path, fake_llm, pipeline_factory):
    empty = tmp_path / "empty"
    empty.mkdir()
    pipeline = pipeline_factory(fake_llm, tmp_path / "none.duckdb", data_dir=empty)
    result = pipeline.run(ECHO_QUESTION)
    assert result["answer_mode"] == "sql_unavailable"
    assert result["sql"]["status"] == "unavailable"
    assert result["dataset"]["date_range"] == {"start": None, "end": None}
    assert fake_llm.calls == []


def test_relative_date_window_anchors_to_dataset_max_date(built_db, fake_llm, pipeline_factory):
    pipeline = pipeline_factory(fake_llm, built_db)
    result = pipeline.run("How many posts were there in the past week?")

    end = date(2025, 2, 18)
    start = end - timedelta(days=7)
    assert date.today() > end  # the wall clock must not matter
    assert result["sql"]["date_window"] == {"start": start.isoformat(), "end": end.isoformat()}
    # The window is bound as parameters, not spliced into the SQL text.
    assert result["sql"]["params"] == [start.isoformat(), end.isoformat()]
    assert result["sql"]["coverage"]["status"] == "full"

    posts = pd.read_csv(REPO_DATA_DIR / "clean_posts.csv", usecols=["created_datetime"])
    days = pd.to_datetime(posts["created_datetime"]).dt.date
    expected = int(((days >= start) & (days <= end)).sum())
    assert expected > 0
    assert result["sql"]["rows"] == [{"post_count": expected}]


def test_web_route_only_when_web_results_exist(built_db, pipeline_factory):
    question = "Explain the narrative about Trump birthright citizenship (use web search)"

    no_web = FakeWeb([])
    llm = FakeLLM()
    result = pipeline_factory(llm, built_db, web=no_web).run(question, web_search=True)
    assert no_web.queries and "(use web search)" not in no_web.queries[0]
    assert result["route"] == "chat_dataset"
    assert not [e for e in result["evidence"] if e["type"] == "web"]
    assert result["retrieval"]["web"] == "duckduckgo_html"

    article = {
        "rank": 1, "title": "Birthright citizenship ruling", "url": "https://example.test/a",
        "source": "example.test", "snippet": "s", "content": "c",
    }
    llm2 = FakeLLM()
    result2 = pipeline_factory(llm2, built_db, web=FakeWeb([article])).run(question, web_search=True)
    assert result2["route"] == "chat_web"
    web_items = [e for e in result2["evidence"] if e["type"] == "web"]
    assert web_items == [
        {"type": "web", "url": "https://example.test/a", "title": "Birthright citizenship ruling",
         "source": "example.test"}
    ]
    assert "https://example.test/a" in llm2.calls[0]["user"]


def test_web_search_without_results_for_unrelated_question(built_db, fake_llm, pipeline_factory):
    result = pipeline_factory(fake_llm, built_db, web=FakeWeb([])).run(OUT_OF_DATASET_QUESTION, web_search=True)
    assert result["route"] == "chat_web_no_results"
    assert result["answer_mode"] == "out_of_dataset"
    assert fake_llm.calls == []
    assert result["evidence"] == []
