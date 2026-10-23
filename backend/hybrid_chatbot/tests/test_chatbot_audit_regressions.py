"""Scope and complete-series regressions found by the backend audit."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest

from conftest import FakeLLM
from hybrid_chatbot.sql_engine import SQLStore, SQLTranslator


@pytest.mark.parametrize("question", [
    "Which subreddit has the highest echo-chamber lift in January 2026?",
    "What are the top domains in r/politics in January 2026?",
    "What is the average score in r/politics in January 2026?",
    "Which narratives are most popular in r/politics in January 2026?",
    "Which subreddits most amplified narrative 0 in January 2026?",
    "How many posts discuss narrative 128?",
    "How many posts in r/politics and r/Conservative?",
    "How many posts in politics and Conservative?",
])
def test_unsupported_scope_never_becomes_a_broader_answer(question, built_db, fake_llm, pipeline_factory):
    result = pipeline_factory(fake_llm, built_db).run(question)
    assert result["answer_mode"] == "insufficient_coverage"
    assert result["sql"]["rows"] == [] and result["evidence"] == []
    assert "No broader result was substituted" in result["answer"]
    assert fake_llm.calls == []
    if "January 2026" in question:
        assert result["sql"]["date_window"] == {"start": "2026-01-01", "end": "2026-01-31"}


@pytest.mark.parametrize("names", [{"politics", "worldpolitics"}, {"worldpolitics", "politics", "Conservative"}])
def test_bare_community_uses_whole_name(names):
    translator = SQLTranslator(names)
    assert translator.build_plan("Top domains in worldpolitics").params == ["worldpolitics"]
    assert translator.build_plan("Top domains in r/worldpolitics").params == ["worldpolitics"]
    assert translator.build_plan("Top domains about geopolitics").params == []


def test_series_evidence_and_prompt_cover_the_complete_interval(built_db, pipeline_factory):
    llm = FakeLLM()
    pipeline = pipeline_factory(llm, built_db)
    result = pipeline.run("Show the overall volume trend over time")
    rows = result["sql"]["rows"]
    assert len(rows) == 201
    assert rows[-1]["date"] == "2025-02-18"
    assert result["evidence"][0]["rows"] == rows
    assert "date=2025-02-18" in llm.calls[0]["user"]
    pipeline.llm = FakeLLM(raises=RuntimeError("offline"))
    fallback = pipeline.run("Show the overall volume trend over time")
    assert "201 observations" in fallback["answer"] and "through 2025-02-18" in fallback["answer"]
    peak = max(rows, key=lambda row: row["post_count"])
    assert f"peak is {peak['post_count']} posts on {peak['date']}" in fallback["answer"]


@pytest.mark.parametrize("serverless", [False, True])
def test_concurrent_reads_have_independent_validation(built_db, tmp_path, monkeypatch, serverless):
    if serverless:
        monkeypatch.setenv("VERCEL", "1")
    store = SQLStore(db_path=tmp_path / "memory.duckdb" if serverless else built_db)
    store.initialize()
    try:
        def read(value):
            return store.execute("SELECT ? AS value", [value]).iloc[0]["value"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            assert list(pool.map(read, range(100))) == list(range(100))
    finally:
        store.close()
