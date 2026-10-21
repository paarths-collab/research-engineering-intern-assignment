"""SQL bootstrap: build, read-only serving, unwritable/serverless fallback, degraded."""

from __future__ import annotations

import os
import threading

import duckdb
import pytest

from conftest import REPO_DATA_DIR
from hybrid_chatbot import build_db, sql_engine
from hybrid_chatbot.config import CSV_TABLES, resolve_data_dir, resolve_db_path
from hybrid_chatbot.sql_engine import SQLStore

EXPECTED_TABLES = sorted(CSV_TABLES.values())

needs_non_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores directory permissions"
)


def test_sql_engine_imports_os():
    # Regression: sql_engine used os.getenv without importing os; the NameError was
    # swallowed so the serverless guard never ran.
    assert hasattr(sql_engine, "os")


def test_fresh_bootstrap_builds_then_serves_read_only(tmp_path):
    db_path = tmp_path / "nested" / "hybrid_chatbot.duckdb"
    assert not db_path.exists()

    first = SQLStore(db_path=db_path, data_dir=REPO_DATA_DIR)
    status = first.initialize()
    assert status.state == "ready"
    assert sorted(status.available_tables) == EXPECTED_TABLES
    assert status.missing_tables == []
    assert status.storage == "file"
    assert db_path.exists()
    assert not list(db_path.parent.glob("*.tmp-*"))  # no half-built leftovers
    assert first.execute("SELECT COUNT(*) AS n FROM echo_chamber_scores").iloc[0]["n"] > 0

    # The serving connection is read-only: a CREATE must be refused.
    with pytest.raises(duckdb.Error):
        first.connect().execute("CREATE TABLE should_not_exist AS SELECT 1")

    # A second store on the same file serves read-only without building anything.
    mtime = db_path.stat().st_mtime_ns
    second = SQLStore(db_path=db_path, data_dir=REPO_DATA_DIR)
    status2 = second.initialize()
    assert status2.state == "ready" and status2.storage == "file"
    with pytest.raises(duckdb.Error):
        second.connect().execute("CREATE TABLE should_not_exist AS SELECT 1")
    assert "should_not_exist" not in sql_engine._list_tables(second.connect())
    assert db_path.stat().st_mtime_ns == mtime
    first.close()
    second.close()


def test_complete_db_in_readonly_file_is_served_without_building(built_db, tmp_path, monkeypatch):
    # Even with a serverless marker and no CSVs at all, a complete DB is just served.
    monkeypatch.setenv("VERCEL", "1")
    calls = []
    monkeypatch.setattr(sql_engine, "build_database", lambda *a, **k: calls.append(a))
    store = SQLStore(db_path=built_db, data_dir=tmp_path / "no_csvs_here")
    status = store.initialize()
    assert status.state == "ready" and status.storage == "file"
    assert calls == []
    store.close()


@needs_non_root
@pytest.mark.parametrize("serverless_env", [False, True])
def test_unwritable_destination_builds_transient_database(tmp_path, monkeypatch, serverless_env):
    dest = tmp_path / "readonly_dir"
    dest.mkdir()
    db_path = dest / "hybrid_chatbot.duckdb"
    if serverless_env:
        monkeypatch.setenv("VERCEL", "1")
    dest.chmod(0o555)
    try:
        store = SQLStore(db_path=db_path, data_dir=REPO_DATA_DIR)
        status = store.initialize()
        assert status.state == "ready", status
        assert status.storage in ("transient_memory", "transient_file")
        assert sorted(status.available_tables) == EXPECTED_TABLES
        assert not db_path.exists()
        assert list(dest.iterdir()) == []
        df = store.execute("SELECT subreddit, lift FROM echo_chamber_scores ORDER BY lift DESC LIMIT 1")
        assert df.iloc[0]["subreddit"] == "Anarchism"
        store.close()
    finally:
        dest.chmod(0o755)


def test_serverless_env_never_writes_to_writable_destination(tmp_path, monkeypatch):
    # VERCEL=1 must route to the transient build even if the directory is writable.
    monkeypatch.setenv("VERCEL", "1")
    db_path = tmp_path / "hybrid_chatbot.duckdb"
    store = SQLStore(db_path=db_path, data_dir=REPO_DATA_DIR)
    status = store.initialize()
    assert status.state == "ready" and status.storage == "transient_memory"
    assert not db_path.exists()
    assert store.execute("SELECT COUNT(*) AS n FROM daily_volume_v2").iloc[0]["n"] == 201
    store.close()


def test_large_csv_set_uses_temp_file(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(sql_engine, "TRANSIENT_MEMORY_MAX_BYTES", 1)
    store = SQLStore(db_path=tmp_path / "x.duckdb", data_dir=REPO_DATA_DIR)
    status = store.initialize()
    assert status.state == "ready" and status.storage == "transient_file"
    transient_dir = store._transient_dir
    assert transient_dir is not None and transient_dir.exists()
    store.close()
    assert not transient_dir.exists()


def test_initialize_is_idempotent_and_thread_safe(tmp_path, monkeypatch):
    real_build = sql_engine.build_database
    calls = []

    def counting_build(*args, **kwargs):
        calls.append(1)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(sql_engine, "build_database", counting_build)
    store = SQLStore(db_path=tmp_path / "t.duckdb", data_dir=REPO_DATA_DIR)
    results = []

    def worker():
        results.append(store.initialize().state)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["ready"] * 8
    assert len(calls) == 1
    conn = store.connect()
    store.initialize()
    assert store.connect() is conn
    store.close()


def test_missing_csv_gives_degraded_status(csv_dir_without, tmp_path):
    csv_dir = csv_dir_without("echo_chamber_scores.csv")
    store = SQLStore(db_path=tmp_path / "d.duckdb", data_dir=csv_dir)
    status = store.initialize()
    assert status.state == "degraded"
    assert status.missing_tables == ["echo_chamber_scores"]
    assert "echo_chamber_scores" not in status.available_tables
    assert len(status.available_tables) == 11
    assert store.missing_for(["echo_chamber_scores", "clean_posts"]) == ["echo_chamber_scores"]
    store.close()


def test_no_csvs_and_no_db_is_unavailable(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    store = SQLStore(db_path=tmp_path / "u.duckdb", data_dir=empty)
    status = store.initialize()
    assert status.state == "unavailable"
    assert status.available_tables == [] and len(status.missing_tables) == 12
    assert status.error
    assert not (tmp_path / "u.duckdb").exists()
    with pytest.raises(sql_engine.SQLUnavailableError):
        store.execute("SELECT 1")
    store.close()


def test_dataset_date_range_is_computed_from_data(built_db):
    store = SQLStore(db_path=built_db, data_dir=REPO_DATA_DIR)
    start, end = store.dataset_date_range()
    assert (start.isoformat(), end.isoformat()) == ("2024-07-23", "2025-02-18")
    assert store.dataset_max_date() == end
    store.close()


def test_db_path_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("HYBRID_SQL_DB_PATH", str(tmp_path / "a.duckdb"))
    assert resolve_db_path() == tmp_path / "a.duckdb"
    monkeypatch.setenv("HYBRID_SQL_DB", str(tmp_path / "b.duckdb"))
    assert resolve_db_path() == tmp_path / "b.duckdb"
    monkeypatch.setenv("HYBRID_DATA_DIR", str(tmp_path))
    assert resolve_data_dir() == tmp_path
    store = SQLStore()
    assert store.db_path == tmp_path / "b.duckdb" and store.data_dir == tmp_path


def test_build_db_cli_reports_row_counts(tmp_path, capsys):
    db_path = tmp_path / "cli.duckdb"
    code = build_db.main(["--db", str(db_path), "--data-dir", str(REPO_DATA_DIR)])
    out = capsys.readouterr().out
    assert code == 0 and db_path.exists()
    for table in EXPECTED_TABLES:
        assert f"{table}:" in out
    assert "daily_volume_v2: 201 rows" in out

    # --force rebuilds in place; the file stays complete.
    assert build_db.main(["--db", str(db_path), "--data-dir", str(REPO_DATA_DIR), "--force"]) == 0
    capsys.readouterr()
    conn = duckdb.connect(str(db_path), read_only=True)
    assert len(sql_engine._list_tables(conn)) == 12
    conn.close()


def test_build_db_cli_fails_when_csv_missing(csv_dir_without, tmp_path, capsys):
    csv_dir = csv_dir_without("clean_posts.csv")
    code = build_db.main(["--db", str(tmp_path / "m.duckdb"), "--data-dir", str(csv_dir)])
    captured = capsys.readouterr()
    assert code == 1
    assert "clean_posts: MISSING" in captured.out
