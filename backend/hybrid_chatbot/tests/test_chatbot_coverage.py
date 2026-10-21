"""Missing data is never zero; no user text reaches SQL; no persona content."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import duckdb
import pytest

from conftest import REPO_DATA_DIR, FakeLLM, make_pipeline
from hybrid_chatbot import pipeline as pipeline_module
from hybrid_chatbot.config import CSV_TABLES
from hybrid_chatbot.sql_engine import SQLStore, SQLTranslator, _list_tables

ECHO_QUESTION = "Which subreddit has the highest echo-chamber lift in the dataset?"


def _strict_json(payload) -> str:
    """Raises on NaN / Infinity, which are not valid JSON."""
    return json.dumps(payload, allow_nan=False)


def _csv_dir_with(tmp_path: Path, name: str, content: str) -> Path:
    target = tmp_path / "csv"
    target.mkdir(exist_ok=True)
    for csv_file in CSV_TABLES:
        shutil.copy(REPO_DATA_DIR / csv_file, target / csv_file)
    (target / name).write_text(content, encoding="utf-8")
    return target


def _assert_no_count(result: dict) -> None:
    assert result["sql"]["rows"] == []
    assert result["evidence"] == []
    assert result["llm_used"] is False


# ── Missing data is not zero ─────────────────────────────────────────────────

@pytest.mark.parametrize(
    "question",
    [
        "How many posts were there between 2023-01-01 and 2023-01-31?",
        "How many posts were there between 2026-03-01 and 2026-03-31?",
        "What was the overall volume trend between 2023-05-01 and 2023-05-31?",
        "When was the biggest spike between 2026-01-01 and 2026-02-01?",
    ],
)
def test_window_outside_dataset_is_insufficient_coverage_not_zero(built_db, fake_llm, pipeline_factory, question):
    result = pipeline_factory(fake_llm, built_db).run(question)

    assert result["answer_mode"] == "insufficient_coverage"
    assert result["route"] == "chat_insufficient_coverage"
    assert result["sql"]["status"] == "insufficient_coverage"
    assert result["sql"]["coverage"]["status"] == "none"
    assert "outside" in result["sql"]["reason"] and "2024-07-23" in result["sql"]["reason"]
    assert "not the same as zero" in result["answer"]
    assert "0 posts" not in result["answer"] and "post_count" not in result["answer"]
    assert fake_llm.calls == []
    _assert_no_count(result)
    _strict_json(result)


def test_window_outside_one_table_but_inside_dataset_names_the_table(built_db, fake_llm, pipeline_factory):
    # graph_edge_intelligence_table only starts on 2024-11-24 even though the dataset starts in July.
    result = pipeline_factory(fake_llm, built_db).run(
        "Which narrative has the highest volume between 2024-08-01 and 2024-08-31?"
    )
    assert result["answer_mode"] == "insufficient_coverage"
    assert "graph_edge_intelligence_table" in result["sql"]["reason"]
    assert "2024-11-24" in result["sql"]["reason"]
    _assert_no_count(result)


def test_genuine_zero_is_reported_as_zero(built_db, fake_llm, pipeline_factory):
    # r/PoliticalDiscussion exists but only has posts from 2025-01-23; the window is inside
    # the dataset's range, so 0 is a real count, not missing data.
    result = pipeline_factory(fake_llm, built_db).run(
        "How many posts in r/PoliticalDiscussion between 2024-08-01 and 2024-08-07?"
    )
    assert result["sql"]["status"] == "ok"
    assert result["sql"]["coverage"]["status"] == "full"
    assert result["sql"]["rows"] == [{"post_count": 0}]
    assert result["answer_mode"] == "llm_synthesis"
    assert len(fake_llm.calls) == 1
    assert "post_count=0" in fake_llm.calls[0]["user"]


def test_partial_window_is_flagged_not_hidden(built_db, fake_llm, pipeline_factory):
    result = pipeline_factory(fake_llm, built_db).run(
        "How many posts were there between 2025-02-10 and 2025-03-10?"
    )
    assert result["sql"]["status"] == "ok"
    assert result["sql"]["coverage"]["status"] == "partial"
    assert result["sql"]["rows"][0]["post_count"] > 0
    assert "extends beyond" in fake_llm.calls[0]["user"]


def test_unknown_subreddit_is_not_zero_posts(built_db, fake_llm, pipeline_factory):
    result = pipeline_factory(fake_llm, built_db).run("How many posts are there in r/doesnotexist?")
    assert result["answer_mode"] == "insufficient_coverage"
    assert "doesnotexist" in result["sql"]["reason"] and "clean_posts" in result["sql"]["reason"]
    assert "0 posts" not in result["answer"]
    assert fake_llm.calls == []
    _assert_no_count(result)


def test_unknown_narrative_is_not_an_empty_ranking(built_db, fake_llm, pipeline_factory):
    result = pipeline_factory(fake_llm, built_db).run("Which subreddits most amplified narrative 99999.0_nowhere.test?")
    assert result["answer_mode"] == "insufficient_coverage"
    assert "narrative_diffusion_table" in result["sql"]["reason"]
    _assert_no_count(result)


def test_unknown_subreddit_domain_ranking_is_not_empty_ranking(built_db, fake_llm, pipeline_factory):
    result = pipeline_factory(fake_llm, built_db).run("What are the top domains in r/nosuchsub?")
    assert result["answer_mode"] == "insufficient_coverage"
    _assert_no_count(result)


def test_bare_month_resolves_against_dataset_not_wall_clock(built_db, fake_llm, pipeline_factory):
    # "September" must mean September 2024 (the latest one at or before 2025-02-18).
    pipeline = pipeline_factory(fake_llm, built_db)
    plan = pipeline.run("How many posts in September?")["sql"]
    assert plan["date_window"] == {"start": "2024-09-01", "end": "2024-09-30"}
    assert plan["coverage"]["status"] == "full"
    # The modal verb "may" is not the month of May.
    assert pipeline.run("Which narrative may have the highest volume?")["sql"]["date_window"] is None


def test_nan_and_inf_never_become_a_ranking(tmp_path, fake_llm, pipeline_factory):
    csv_dir = _csv_dir_with(
        tmp_path, "echo_chamber_scores.csv", "subreddit,lift\nbadnan,nan\nbadinf,inf\nnull,\ngood,5.5\nlower,1.25\n"
    )
    result = pipeline_factory(fake_llm, tmp_path / "nan.duckdb", data_dir=csv_dir).run(ECHO_QUESTION)

    assert result["answer_mode"] == "deterministic_sql"
    assert "good" in result["answer"] and "5.500000" in result["answer"]
    assert result["sql"]["rows"] == [{"subreddit": "good", "lift": 5.5}]
    blob = _strict_json(result).lower()
    for token in ("nan", "infinity", "badinf", "badnan"):
        assert token not in blob.replace("finance", "")  # ranking and snippets exclude them


def test_all_values_missing_is_insufficient_coverage(tmp_path, fake_llm, pipeline_factory):
    csv_dir = _csv_dir_with(tmp_path, "echo_chamber_scores.csv", "subreddit,lift\na,nan\nb,inf\nc,\n")
    result = pipeline_factory(fake_llm, tmp_path / "allnan.duckdb", data_dir=csv_dir).run(ECHO_QUESTION)
    assert result["answer_mode"] == "insufficient_coverage"
    assert result["sql"]["rows"] == []
    assert fake_llm.calls == []
    _strict_json(result)


def test_null_average_is_insufficient_coverage(tmp_path, fake_llm, pipeline_factory):
    csv_dir = _csv_dir_with(
        tmp_path,
        "subreddit_intelligence_summary.csv",
        "subreddit,total_duplicate_posts,unique_narratives,unique_users,avg_score,domain,lift\n"
        "a,1,1,1,,x.com,1.0\nb,1,1,1,nan,y.com,2.0\n",
    )
    result = pipeline_factory(fake_llm, tmp_path / "avg.duckdb", data_dir=csv_dir).run("What is the average score?")
    assert result["answer_mode"] == "insufficient_coverage"
    assert fake_llm.calls == []
    _strict_json(result)


def test_json_serialisable_for_sql_answers_with_integers(built_db, fake_llm, pipeline_factory):
    result = pipeline_factory(fake_llm, built_db).run("How many posts were there in the past week?")
    _strict_json(result["sql"])
    assert type(result["sql"]["rows"][0]["post_count"]) is int


# ── No free-form SQL ─────────────────────────────────────────────────────────

INJECTIONS = [
    "Top domains in r/politics'; DROP TABLE echo_chamber_scores; --",
    "Trend of narrative 1.0'; DROP TABLE clean_posts; -- over time",
    "How many posts in r/politics' OR '1'='1'; DROP TABLE daily_volume_v2; --",
    "'; DROP TABLE x; --",
    "highest echo lift'); DROP TABLE echo_chamber_scores; --",
]


def _table_counts(store: SQLStore) -> dict[str, int]:
    return {t: int(store.execute(f"SELECT COUNT(*) AS n FROM {t}").iloc[0]["n"]) for t in CSV_TABLES.values()}


@pytest.mark.parametrize("serverless", [False, True], ids=["file_db", "transient_memory_db"])
@pytest.mark.parametrize("question", INJECTIONS)
def test_injection_shaped_query_is_not_executed(built_db, tmp_path, monkeypatch, pipeline_factory, serverless, question):
    if serverless:
        # transient in-memory DB: the serving connection is writable, so a DROP would succeed
        monkeypatch.setenv("VERCEL", "1")
        db_path = tmp_path / "unused.duckdb"
    else:
        db_path = built_db
    pipeline = pipeline_factory(FakeLLM(), db_path)
    before = _table_counts(pipeline.sql_store)
    assert len(before) == 12

    result = pipeline.run(question)

    assert _table_counts(pipeline.sql_store) == before
    plan = pipeline.sql_translator.build_plan(question, reference_date=None)
    if plan is not None:
        for fragment in ("DROP", "--", "OR '1'", "'"):
            assert fragment not in plan.sql.replace("ESCAPE '\\'", "")
    assert "DROP" not in (result["sql"]["query"] or "")
    _strict_json(result)
    if not serverless:
        conn = duckdb.connect(str(built_db), read_only=True)
        assert len(_list_tables(conn)) == 12
        conn.close()


def test_hostile_identifier_in_valid_names_is_bound_not_spliced(built_db):
    # Even if a stored subreddit name contained SQL, it is only ever a bound parameter.
    hostile = "evil'; DROP TABLE echo_chamber_scores; --"
    store = SQLStore(db_path=built_db, data_dir=REPO_DATA_DIR)
    plan = SQLTranslator({hostile}).build_plan(f"What are the top domains in {hostile}?")

    assert plan is not None and plan.params == [hostile]
    assert "evil" not in plan.sql and "DROP" not in plan.sql
    assert store.check_coverage(plan).status == "none"  # no such subreddit; and nothing was executed
    assert store.execute(plan.sql, plan.params).empty
    assert "echo_chamber_scores" in _list_tables(store.connect())
    store.close()


def test_execute_refuses_anything_but_a_single_select(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")  # writable in-memory database
    store = SQLStore(db_path=tmp_path / "x.duckdb", data_dir=REPO_DATA_DIR)
    for bad in (
        "DROP TABLE echo_chamber_scores",
        "SELECT 1; DROP TABLE echo_chamber_scores",
        "DELETE FROM clean_posts",
        "CREATE TABLE t AS SELECT 1",
    ):
        with pytest.raises(ValueError):
            store.execute(bad)
    assert "echo_chamber_scores" in _list_tables(store.connect())
    assert store.execute("SELECT COUNT(*) AS n FROM echo_chamber_scores").iloc[0]["n"] > 0
    store.close()


def test_plans_carry_user_values_only_as_parameters(built_db):
    translator = SQLTranslator({"politics"})
    plan = translator.build_plan("How many posts in r/politics between 2025-01-01 and 2025-01-31?")
    assert plan.params == ["politics", "2025-01-01", "2025-01-31"]
    assert "politics" not in plan.sql and "2025" not in plan.sql
    assert plan.sql.count("?") == len(plan.params)


# ── No persona / perspective simulation in the chatbot ───────────────────────

def test_chatbot_answers_contain_no_persona_simulation(built_db, pipeline_factory):
    llm = FakeLLM()
    pipeline = pipeline_factory(llm, built_db)
    results = [
        pipeline.run("Explain the narrative about Trump birthright citizenship from salon.com"),
        pipeline.run(ECHO_QUESTION),
    ]
    prompts = " ".join(c["system"] + c["user"] for c in llm.calls).lower()
    assert llm.calls
    for word in ("persona", "perspective", "simulat", "role-play", "roleplay"):
        assert word not in prompts
        for r in results:
            assert word not in r["answer"].lower()
    package_dir = Path(pipeline_module.__file__).parent
    for module in package_dir.glob("*.py"):
        text = module.read_text(encoding="utf-8").lower()
        for word in ("persona", "perspective", "simulat"):
            assert word not in text, f"{module.name} mentions {word}"
