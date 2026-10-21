"""`SQLStore.execute` only ever runs exactly one parsed SELECT: no data-modifying
CTEs, no stacked statements, no file/URL table functions. Failed attempts must leave
every table untouched (checked on file-backed and transient in-memory databases)."""

from __future__ import annotations

import duckdb
import pytest

from conftest import REPO_DATA_DIR
from hybrid_chatbot.config import CSV_TABLES
from hybrid_chatbot.sql_engine import SQLStore, _assert_single_select

TABLES = sorted(CSV_TABLES.values())

# Every entry must be refused.
REJECTED = {
    "cte_delete": "WITH x AS (SELECT 1) DELETE FROM echo_chamber_scores",
    "cte_insert": "WITH x AS (SELECT 1 AS subreddit) INSERT INTO echo_chamber_scores SELECT * FROM echo_chamber_scores",
    "cte_update": "WITH x AS (SELECT 1) UPDATE echo_chamber_scores SET lift = 0",
    "plain_delete": "DELETE FROM echo_chamber_scores",
    "drop": "DROP TABLE echo_chamber_scores",
    "create_table_as": "CREATE TABLE leak AS SELECT * FROM echo_chamber_scores",
    "stacked": "SELECT 1; DELETE FROM echo_chamber_scores",
    "stacked_after_comment": "SELECT 1 -- ;\n; DELETE FROM echo_chamber_scores",
    "stacked_after_block_comment": "SELECT 1 /* ; */; DELETE FROM echo_chamber_scores",
    "two_selects": "SELECT 1; SELECT 2",
    "read_text": "SELECT * FROM read_text('/etc/hostname')",
    "read_text_scalar_position": "SELECT content FROM read_text('/etc/hostname') LIMIT 1",
    "read_csv": "SELECT * FROM read_csv('/etc/hosts')",
    "read_csv_auto": "SELECT * FROM read_csv_auto('/etc/hosts')",
    "read_parquet": "SELECT * FROM read_parquet('/tmp/nope.parquet')",
    "read_json": "SELECT * FROM read_json('/tmp/nope.json')",
    "read_blob": "SELECT * FROM read_blob('/etc/hosts')",
    "glob": "SELECT * FROM glob('/etc/*')",
    "table_function_in_cte": "WITH f AS (SELECT * FROM read_text('/etc/hostname')) SELECT * FROM f",
    "table_function_in_subquery": "SELECT * FROM echo_chamber_scores WHERE subreddit IN (SELECT content FROM read_text('/etc/hostname'))",
    "system_table_function": "SELECT * FROM duckdb_settings()",
    "file_replacement_scan": "SELECT * FROM '/etc/hosts.csv'",
    "quoted_path_table": 'SELECT * FROM "/tmp/anything.parquet"',
    "information_schema": "SELECT * FROM information_schema.tables",
    "internal_view": "SELECT * FROM duckdb_tables",
    "unknown_table": "SELECT * FROM not_a_chatbot_table",
    "attach": "ATTACH '/tmp/other.duckdb' AS other",
    "copy_out": "COPY echo_chamber_scores TO '/tmp/leak.csv'",
    "set": "SET enable_external_access=true",
    "pragma": "PRAGMA database_list",
    "describe": "DESCRIBE echo_chamber_scores",
    "explain": "EXPLAIN SELECT 1",
    "empty": "",
    "comment_only": "-- nothing here",
    "garbage": "SELEC 1 FROM",
}


def _counts(store: SQLStore) -> dict[str, int]:
    cursor = store.connect().cursor()
    try:
        return {t: cursor.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    finally:
        cursor.close()


@pytest.fixture(params=["file_db", "transient_memory_db"])
def store(request, built_db, monkeypatch, tmp_path):
    if request.param == "file_db":
        s = SQLStore(db_path=built_db, data_dir=REPO_DATA_DIR)
    else:
        monkeypatch.setenv("VERCEL", "1")  # writable in-memory database built from the CSVs
        s = SQLStore(db_path=tmp_path / "unused.duckdb", data_dir=REPO_DATA_DIR)
    status = s.initialize()
    assert status.state == "ready"
    assert status.storage == ("file" if request.param == "file_db" else "transient_memory")
    yield s
    s.close()


@pytest.mark.parametrize("name", sorted(REJECTED))
def test_execute_rejects_and_leaves_tables_untouched(store, name):
    before = _counts(store)
    assert all(n > 0 for n in before.values())

    with pytest.raises((ValueError, duckdb.Error)):
        store.execute(REJECTED[name])

    assert _counts(store) == before
    assert "leak" not in {t.lower() for t in sql_tables(store)}


def sql_tables(store: SQLStore) -> set[str]:
    cursor = store.connect().cursor()
    try:
        return {r[0] for r in cursor.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    finally:
        cursor.close()


@pytest.mark.parametrize("name", sorted(REJECTED))
def test_guard_rejects_without_touching_the_database(name):
    # the guard itself (no store): parse-only, so it can never run the statement
    with pytest.raises(ValueError):
        _assert_single_select(REJECTED[name], allowed_tables=set(TABLES))


def test_table_function_is_refused_even_when_nested(store):
    with pytest.raises(ValueError, match="Table functions"):
        store.execute("SELECT 1 FROM echo_chamber_scores WHERE EXISTS (SELECT * FROM read_text('/etc/hostname'))")


def test_serving_connection_cannot_reach_files_even_if_the_guard_were_bypassed(store):
    # defence in depth: external access is switched off and locked on the serving connection
    conn = store.connect()
    with pytest.raises(duckdb.Error):
        conn.execute("SELECT * FROM read_text('/etc/hostname')").fetchall()
    with pytest.raises(duckdb.Error):
        conn.execute("SET enable_external_access=true")


@pytest.mark.parametrize(
    "sql, params",
    [
        ("SELECT COUNT(*) AS n FROM echo_chamber_scores", None),
        ("SELECT 1 -- ;", None),  # a ';' inside a comment is not a second statement
        ("SELECT 'a;b' AS s", None),
        ("SELECT subreddit FROM echo_chamber_scores WHERE subreddit ILIKE ? ESCAPE '\\' LIMIT 1", ["%a%"]),
        ("WITH x AS (SELECT subreddit FROM echo_chamber_scores) SELECT COUNT(*) AS n FROM x;", None),
        ("SELECT a.subreddit FROM echo_chamber_scores a JOIN echo_chamber_scores b ON a.subreddit = b.subreddit LIMIT 1", None),
        ("SELECT COUNT(*) FROM main.echo_chamber_scores", None),
    ],
)
def test_legitimate_selects_still_run(store, sql, params):
    before = _counts(store)
    df = store.execute(sql, params)
    assert len(df) >= 1
    assert _counts(store) == before


def test_every_planner_template_passes_the_guard(store):
    # every question shape the translator can produce must still be accepted
    translator_questions = [
        "When did narrative 128_blackrosefed.org spike?",
        "Which narrative spiked in January 2025?",
        "top domains in r/politics",
        "highest echo chamber score",
        "dominant narratives in r/politics",
        "Which subreddits most amplified narrative 0.0_salon.com?",
        "highest narrative volume",
        "trend of narrative 128_blackrosefed.org over time",
        "overall volume trend",
        "how many posts in r/politics in January 2025",
        "average score for r/politics",
    ]
    from hybrid_chatbot.sql_engine import SQLTranslator

    translator = SQLTranslator(store.valid_subreddits())
    seen = 0
    for question in translator_questions:
        plan = translator.build_plan(question, store.dataset_max_date())
        if plan is None:
            continue
        store.execute(plan.sql, plan.params)
        seen += 1
    assert seen >= 8
