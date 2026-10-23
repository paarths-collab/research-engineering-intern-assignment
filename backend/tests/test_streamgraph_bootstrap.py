"""Fresh fallback startup must serve the bundled ecosystem, without live services."""
import asyncio
from pathlib import Path

import pytest

from streamgraph2.data import db
from streamgraph2.logic import media_ecosystem


@pytest.fixture
def fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DUCKDB_PATH", tmp_path / "stream.duckdb")
    monkeypatch.setattr(db, "_DATA_DIR", Path(__file__).resolve().parents[2] / "data")
    monkeypatch.setattr(db, "_duck_conn", None)
    monkeypatch.setattr(db, "_pool", None)
    yield
    asyncio.run(db.close_pool())


def test_fresh_fallback_serves_all_ecosystem_consumers(fallback):
    async def check():
        await db.init_pool()
        subs = await media_ecosystem.get_all_subreddits()
        assert len(subs) == 10 and "politics" in subs
        assert await media_ecosystem.get_echo_scores()
        assert (await media_ecosystem.get_similarity_matrix())["subreddits"] == subs
        assert await media_ecosystem.get_top_domains("politics")
        assert await media_ecosystem.get_category_breakdown("politics")
        assert (await media_ecosystem.build_llm_payload("politics"))["top_domains"]
    asyncio.run(check())


def test_restart_preserves_persisted_metrics(fallback):
    asyncio.run(db.init_pool())
    db._duck_conn.execute("UPDATE echo_chamber_scores SET echo_score = 123 WHERE subreddit = 'politics'")
    counts = [db._duck_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
              for table in ("echo_chamber_scores", "subreddit_domain_flow", "top_distinctive_domains")]
    asyncio.run(db.close_pool())
    asyncio.run(db.init_pool())
    assert db._duck_conn.execute("SELECT echo_score FROM echo_chamber_scores WHERE subreddit = 'politics'").fetchone()[0] == 123
    assert counts == [db._duck_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("echo_chamber_scores", "subreddit_domain_flow", "top_distinctive_domains")]
