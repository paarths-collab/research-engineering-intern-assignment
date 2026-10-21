"""Ranking templates are deterministic (tie-broken, ties at the cut-off disclosed) and
SQL values are rendered as plain dates / integers."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from conftest import REPO_DATA_DIR, FakeLLM, FakeWeb
from hybrid_chatbot.dataset_context import DatasetContextStore
from hybrid_chatbot.pipeline import ChatPipeline, _clean_value
from hybrid_chatbot.sql_engine import SQLStore, SQLTranslator

DOMAIN_QUESTION = "What are the top domains?"
ECHO_QUESTION = "Which subreddit has the highest echo-chamber lift in the dataset?"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@pytest.fixture
def csv_pipeline(tmp_path):
    """Pipeline over one hand-written CSV (table name = file stem), DB under tmp_path."""
    created: list[ChatPipeline] = []

    def factory(csv_name: str, content: str, llm=None) -> ChatPipeline:
        data_dir = tmp_path / f"csv{len(created)}"
        data_dir.mkdir()
        (data_dir / csv_name).write_text(content, encoding="utf-8")
        store = SQLStore(
            db_path=tmp_path / f"db{len(created)}.duckdb",
            data_dir=data_dir,
            csv_tables={csv_name: Path(csv_name).stem},
        )
        pipeline = ChatPipeline(
            llm or FakeLLM(), sql_store=store, dataset_store=DatasetContextStore(data_dir=data_dir), web=FakeWeb()
        )
        created.append(pipeline)
        return pipeline

    yield factory
    for pipeline in created:
        pipeline.sql_store.close()


def _domain_csv(counts: dict[str, int]) -> str:
    return "subreddit,domain,count\n" + "".join(f"politics,{d},{n}\n" for d, n in counts.items())


# ── Ties: deterministic order ────────────────────────────────────────────────

def test_every_ordered_template_has_a_tie_breaker():
    translator = SQLTranslator({"politics"})
    queries = [
        "When did narrative 0_salon.com spike?",
        "When did the volume spike?",
        "What are the top domains?",
        "Which subreddit has the highest echo chamber score?",
        "Which echo chamber scores are there?",
        "What are the dominant narratives in r/politics?",
        "Which subreddits most amplified narrative 0_salon.com?",
        "Which narrative has the highest volume?",
        "Show the trend of narrative 0_salon.com over time",
        "Show the volume trend over time",
    ]
    for query in queries:
        plan = translator.build_plan(query)
        assert plan is not None, query
        order_by = plan.sql.split("ORDER BY", 1)[1].split("LIMIT")[0]
        assert "," in order_by or "date ASC" in order_by, (query, plan.sql)
        if plan.limit:
            assert plan.rank_by and plan.tie_break, query


def test_top_domains_are_identical_across_freshly_built_dbs_and_tie_ordered(tmp_path, pipeline_factory):
    runs = [
        pipeline_factory(FakeLLM(), tmp_path / f"fresh{i}.duckdb").run(DOMAIN_QUESTION)["sql"]["rows"] for i in range(2)
    ]
    assert runs[0] == runs[1]
    domains = [r["domain"] for r in runs[0]]
    counts = {r["domain"]: r["total_count"] for r in runs[0]}
    # nytimes.com and youtu.be tie at 144 in the real data: ascending domain decides.
    assert counts["nytimes.com"] == counts["youtu.be"] == 144
    assert domains.index("nytimes.com") < domains.index("youtu.be")
    assert [(-r["total_count"], r["domain"]) for r in runs[0]] == sorted((-r["total_count"], r["domain"]) for r in runs[0])


def test_tie_order_does_not_depend_on_file_order(csv_pipeline):
    forward = csv_pipeline("subreddit_domain_flow_v2.csv", _domain_csv({"b.com": 5, "a.com": 5, "c.com": 9}))
    reverse = csv_pipeline("subreddit_domain_flow_v2.csv", _domain_csv({"c.com": 9, "a.com": 5, "b.com": 5}))
    rows = forward.run(DOMAIN_QUESTION)["sql"]["rows"]
    assert [r["domain"] for r in rows] == ["c.com", "a.com", "b.com"]
    assert reverse.run(DOMAIN_QUESTION)["sql"]["rows"] == rows


# ── Ties at the LIMIT boundary are disclosed ─────────────────────────────────

def test_tie_across_the_limit_is_noted_in_sql_and_answer(csv_pipeline):
    # dom10.com and dom11.com tie for rank 10/11; the cut-off keeps only dom10.com.
    counts = {"dom11.com": 5, "dom12.com": 1}
    counts.update({f"dom{i:02d}.com": 100 - i for i in range(1, 10)})
    counts["dom10.com"] = 5
    result = csv_pipeline("subreddit_domain_flow_v2.csv", _domain_csv(counts)).run(DOMAIN_QUESTION)

    rows = result["sql"]["rows"]
    assert len(rows) == 10 and rows[-1]["domain"] == "dom10.com"
    assert "dom11.com" not in [r["domain"] for r in rows]
    notes = result["sql"]["notes"]
    assert len(notes) == 1
    assert "Tie at the result boundary" in notes[0]
    assert "ranks 10 and 11" in notes[0] and "total_count (5)" in notes[0] and "domain" in notes[0]
    assert notes[0] in result["answer"]


def test_no_boundary_note_when_the_cut_falls_between_distinct_values(csv_pipeline):
    # a tie exists inside the list (ranks 3/4) but not across the cut-off
    counts = {f"dom{i:02d}.com": 100 - i for i in range(1, 12)}
    counts["dom04.com"] = counts["dom03.com"]
    result = csv_pipeline("subreddit_domain_flow_v2.csv", _domain_csv(counts)).run(DOMAIN_QUESTION)

    assert len(result["sql"]["rows"]) == 10
    assert result["sql"]["notes"] == []


def test_no_boundary_note_when_fewer_rows_than_the_limit(csv_pipeline):
    result = csv_pipeline("subreddit_domain_flow_v2.csv", _domain_csv({"a.com": 5, "b.com": 5})).run(DOMAIN_QUESTION)
    assert [r["domain"] for r in result["sql"]["rows"]] == ["a.com", "b.com"]
    assert result["sql"]["notes"] == []


@pytest.mark.parametrize("csv_text", ["subreddit,lift\nzeta,2.5\nalpha,2.5\nmid,1.0\n", "subreddit,lift\nmid,1.0\nalpha,2.5\nzeta,2.5\n"])
def test_top_one_tie_picks_the_first_key_and_says_so(csv_pipeline, csv_text):
    result = csv_pipeline("echo_chamber_scores.csv", csv_text).run(ECHO_QUESTION)

    assert result["sql"]["rows"] == [{"subreddit": "alpha", "lift": 2.5}]
    assert "alpha" in result["answer"]
    assert any("Tie at the result boundary" in n and "ranks 1 and 2" in n for n in result["sql"]["notes"])
    assert result["sql"]["notes"][0] in result["answer"]


def test_unique_top_one_has_no_tie_note(csv_pipeline):
    result = csv_pipeline("echo_chamber_scores.csv", "subreddit,lift\nzeta,2.5\nalpha,2.0\n").run(ECHO_QUESTION)
    assert result["sql"]["rows"] == [{"subreddit": "zeta", "lift": 2.5}]
    assert result["sql"]["notes"] == []


# ── Dates are plain ISO dates ────────────────────────────────────────────────

def test_clean_value_renders_dates_and_midnight_timestamps_as_plain_dates():
    assert _clean_value(pd.Timestamp("2025-02-14")) == "2025-02-14"
    assert _clean_value(datetime(2025, 2, 14)) == "2025-02-14"
    assert _clean_value(date(2025, 2, 14)) == "2025-02-14"
    # a real time of day is kept
    assert _clean_value(pd.Timestamp("2025-02-14 13:45:00")) == "2025-02-14T13:45:00"
    assert _clean_value(pd.NaT) is None


def test_sql_rows_evidence_and_answer_use_plain_dates(built_db, pipeline_factory):
    llm = FakeLLM(raises=RuntimeError("no llm"))  # fallback answer quotes the SQL rows
    result = pipeline_factory(llm, built_db).run("Show the volume trend over time")

    rows = result["sql"]["rows"]
    assert rows and all(ISO_DATE.match(r["date"]) for r in rows)
    sql_evidence = [e for e in result["evidence"] if e["type"] == "sql"]
    assert sql_evidence and all(ISO_DATE.match(r["date"]) for r in sql_evidence[0]["rows"])
    assert "T00:00:00" not in result["answer"]
    assert f"date={rows[0]['date']}," in result["answer"]  # "date=2024-07-23, post_count=..."


def test_spike_date_is_a_plain_date(built_db, pipeline_factory):
    result = pipeline_factory(FakeLLM(), built_db).run("When did the volume spike?")
    assert ISO_DATE.match(result["sql"]["rows"][0]["date"])


# ── Integers stay integers; genuine floats are untouched ─────────────────────

def test_integer_sums_render_as_integers(built_db, pipeline_factory):
    llm = FakeLLM(raises=RuntimeError("no llm"))
    result = pipeline_factory(llm, built_db).run(DOMAIN_QUESTION)

    rows = result["sql"]["rows"]
    assert all(type(r["total_count"]) is int for r in rows)
    expected = pd.read_csv(REPO_DATA_DIR / "subreddit_domain_flow_v2.csv").groupby("domain")["count"].sum()
    assert rows[0]["total_count"] == expected[rows[0]["domain"]]
    assert f"total_count={rows[0]['total_count']};" in result["answer"]
    assert not re.search(r"total_count=\d+\.0\b", result["answer"])


def test_genuine_floats_are_not_rounded(built_db, pipeline_factory):
    echo = pipeline_factory(FakeLLM(), built_db).run(ECHO_QUESTION)["sql"]["rows"][0]
    assert echo["lift"] == 26.704058011434945
    assert _clean_value(2.5) == 2.5
    assert _clean_value(3.0) == 3.0  # no source-column knowledge here: never silently rounded
    average = pipeline_factory(FakeLLM(), built_db).run("What is the average score?")["sql"]["rows"][0]["avg_score"]
    assert isinstance(average, float) and not float(average).is_integer()
