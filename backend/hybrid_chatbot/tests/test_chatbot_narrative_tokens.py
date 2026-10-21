"""A narrative entity is only recognised from an id-shaped token; ordinary words after
"narrative" are not ids. Unparseable time phrases are disclosed, not silently dropped."""

from __future__ import annotations

import pytest

from conftest import FakeLLM
from hybrid_chatbot.sql_engine import (
    SQLTranslator,
    _extract_narrative_token,
    _narrative_like,
)

# Real ids: graph_edge_intelligence_table uses "<cluster>_<domain>"; narrative_registry /
# narrative_diffusion_table use "<cluster>.0_<domain>" (or "<domain>_<domain>").
GRAPH_ID = "128_blackrosefed.org"
DIFFUSION_ID = "0.0_salon.com"

NO_ENTITY_QUERIES = [
    ("Which narrative spiked in January 2025?", "spiked"),
    ("Show me the trend of the narrative over time", "over"),
    ("Which subreddits most amplified the narrative about Trump?", "about"),
]


def _translator() -> SQLTranslator:
    return SQLTranslator({"politics"})


@pytest.mark.parametrize("query, word", NO_ENTITY_QUERIES)
def test_plain_words_after_narrative_are_not_ids(query, word):
    assert _extract_narrative_token(query) is None
    plan = _translator().build_plan(query)
    assert plan is not None
    assert not [e for e in plan.entities if e.label == "narrative"]
    assert all(word not in str(p).lower() for p in plan.params)
    assert "narrative_id ILIKE" not in plan.sql


@pytest.mark.parametrize("query, word", NO_ENTITY_QUERIES)
def test_no_false_coverage_failure_or_scoped_success(built_db, pipeline_factory, query, word):
    result = pipeline_factory(FakeLLM(), built_db).run(query)

    assert result["answer_mode"] != "insufficient_coverage"
    assert result["sql"]["status"] != "insufficient_coverage"
    assert "does not appear" not in result["answer"]
    assert all(word not in str(p).lower() for p in result["sql"]["params"])
    assert result["sql"]["coverage"]["status"] in ("not_applicable", "full", "partial")
    if word == "about":
        # an unresolved topic must be disclosed, not presented as a scoped answer
        assert any("No narrative filter was applied" in n for n in result["sql"]["notes"])
        assert "No narrative filter was applied" in result["answer"]


@pytest.mark.parametrize(
    "query, expected",
    [
        (f"Show the trend of narrative {GRAPH_ID} over time", GRAPH_ID),
        (f"Which subreddits most amplified narrative {DIFFUSION_ID}?", DIFFUSION_ID),
        (f"When did {GRAPH_ID} spike?", GRAPH_ID),  # id-shaped even without the word "narrative"
        ("Which subreddits most amplified narrative id 128?", "N128"),
        ("When did narrative 128 spike?", "N128"),
        ("When did narrative #7 spike?", "N7"),
        ("trend for N42", "N42"),
        ("trend of narrative salon.com over time", "salon.com"),
        ("trend of narrative 'salon' over time", "salon"),
        ('trend of narrative "Excluding Indians" over time', "Excluding Indians"),
        ("trend of narrative id latimes.com_latimes.com.", "latimes.com_latimes.com"),
    ],
)
def test_id_shaped_tokens_are_recognised(query, expected):
    assert _extract_narrative_token(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "the narrative is growing",
        "any narrative that spiked in 2025?",
        "narrative id is unknown",
        "How did the narrative 2025 look?",
        "narrative. Over time?",
        "narratives about Trump",
    ],
)
def test_non_ids_are_not_recognised(query):
    assert _extract_narrative_token(query) is None


def test_like_patterns_follow_each_tables_id_format():
    graph, diffusion = "graph_edge_intelligence_table", "narrative_diffusion_table"
    assert _narrative_like("N128", graph) == "128\\_%"
    assert _narrative_like("N128", diffusion) == "128.%"
    assert _narrative_like(GRAPH_ID, graph) == "128\\_blackrosefed.org"
    assert _narrative_like(GRAPH_ID, diffusion) == "128.%\\_blackrosefed.org"
    assert _narrative_like(DIFFUSION_ID, graph) == "0\\_salon.com"
    assert _narrative_like(DIFFUSION_ID, diffusion) == "0.%\\_salon.com"
    assert _narrative_like("100%_x", graph) == "%100\\%\\_x%"


def test_real_graph_edge_id_resolves(built_db, pipeline_factory):
    result = pipeline_factory(FakeLLM(), built_db).run(f"Show the trend of narrative {GRAPH_ID} over time")

    assert result["sql"]["status"] == "ok"
    assert result["sql"]["tables"] == ["graph_edge_intelligence_table"]
    assert result["sql"]["params"] == ["128\\_blackrosefed.org"]
    assert result["sql"]["coverage"]["status"] == "full"
    assert result["sql"]["rows"]


def test_bare_cluster_number_resolves_in_graph_edge_table(built_db, pipeline_factory):
    # "N<digit>" used to become '128.%', which no graph_edge id matches
    result = pipeline_factory(FakeLLM(), built_db).run("When did narrative 128 spike?")

    assert result["sql"]["status"] == "ok"
    assert result["sql"]["params"][0] == "128\\_%"
    assert result["sql"]["rows"]


def test_real_diffusion_id_resolves(built_db, pipeline_factory):
    result = pipeline_factory(FakeLLM(), built_db).run(f"Which subreddits most amplified narrative {DIFFUSION_ID}?")

    assert result["sql"]["status"] == "ok"
    assert result["sql"]["tables"] == ["narrative_diffusion_table"]
    assert result["sql"]["rows"]


def test_diffusion_table_accepts_cluster_number_and_graph_style_id(built_db, pipeline_factory):
    by_number = pipeline_factory(FakeLLM(), built_db).run("Which subreddits most amplified narrative 0?")
    by_graph_id = pipeline_factory(FakeLLM(), built_db).run(
        "Which subreddits most amplified narrative 0_salon.com?"
    )
    assert by_number["sql"]["status"] == "ok" and by_number["sql"]["rows"]
    assert by_graph_id["sql"]["status"] == "ok" and by_graph_id["sql"]["rows"]


@pytest.mark.parametrize("query, shown", [
    ("Show the trend of narrative 99999_nowhere.example over time", "99999_nowhere.example"),
    ("When did narrative 9999 spike?", "N9999"),
])
def test_missing_narrative_message_uses_the_name_the_user_gave(built_db, pipeline_factory, query, shown):
    result = pipeline_factory(FakeLLM(), built_db).run(query)

    assert result["answer_mode"] == "insufficient_coverage"
    assert f"narrative '{shown}' does not appear" in result["answer"]
    assert "'9999.'" not in result["answer"] and "'99999." not in result["answer"]


# ── Unparseable time phrases are disclosed ───────────────────────────────────

def test_unparsed_time_phrase_is_disclosed(built_db, pipeline_factory):
    result = pipeline_factory(FakeLLM(), built_db).run("How many posts were there in mid-may?")

    assert result["sql"]["date_window"] is None
    assert result["sql"]["status"] == "ok"
    assert result["sql"]["notes"] and "No date filter was applied" in result["sql"]["notes"][0]
    assert "mid-may" in result["sql"]["notes"][0]
    assert "No date filter was applied" in result["answer"]


@pytest.mark.parametrize(
    "query",
    [
        "How many posts were there in January 2025?",  # parsed
        "How many posts were there in r/politics?",  # no time reference
        "Which narratives may have spiked?",  # modal verb, not May
        "How many posts were there between 2025-01-01 and 2025-01-31?",  # parsed
    ],
)
def test_no_note_when_nothing_was_dropped(query):
    plan = _translator().build_plan(query)
    assert plan is not None
    assert plan.notes == []


@pytest.mark.parametrize("query", ["how many posts in Q3 2025", "how many posts this quarter", "how many posts on 2025-02-13"])
def test_other_unparsed_time_references_are_disclosed(query):
    plan = _translator().build_plan(query)
    assert plan is not None and plan.date_range is None
    assert plan.notes and "No date filter was applied" in plan.notes[0]
