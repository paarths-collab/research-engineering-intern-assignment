"""Shared fixtures for the hybrid_chatbot tests.

No network, no live LLM: the LLM and web search are replaced with fakes, and every
DuckDB file is built under pytest's tmp_path (never inside the repo).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DATA_DIR = BACKEND_DIR.parent / "data"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from hybrid_chatbot.config import CSV_TABLES  # noqa: E402
from hybrid_chatbot.dataset_context import DatasetContextStore  # noqa: E402
from hybrid_chatbot.pipeline import ChatPipeline  # noqa: E402
from hybrid_chatbot.sql_engine import SQLStore  # noqa: E402

ENV_VARS = (
    "HYBRID_SQL_DB",
    "HYBRID_SQL_DB_PATH",
    "HYBRID_DATA_DIR",
    "DATA_PATH",
    "DATA_DIR",
    "VERCEL",
    "AWS_LAMBDA_FUNCTION_NAME",
    "HYBRID_REBUILD_SQL",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


class FakeLLM:
    """Records calls and returns a fixed string (or raises)."""

    def __init__(self, reply: str = "Fake LLM synthesis.", raises: Exception | None = None):
        self.reply = reply
        self.raises = raises
        self.calls: list[dict] = []
        self.api_key = "fake"
        self.model = "fake-model"
        self.base_url = "http://fake.invalid"

    def generate(self, system_prompt, user_prompt, max_tokens=400):
        self.calls.append({"system": system_prompt, "user": user_prompt, "max_tokens": max_tokens})
        if self.raises:
            raise self.raises
        return self.reply, 0.01


class FakeWeb:
    enabled = True

    def __init__(self, results: list[dict] | None = None):
        self.results = results or []
        self.queries: list[str] = []

    def search_and_scrape(self, query, max_results=4):
        self.queries.append(query)
        return list(self.results)


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture(scope="session")
def built_db(tmp_path_factory) -> Path:
    """A complete DB built once from the real CSVs, in a temp dir."""
    path = tmp_path_factory.mktemp("dbs") / "hybrid_chatbot.duckdb"
    store = SQLStore(db_path=path, data_dir=REPO_DATA_DIR)
    assert store.initialize().state == "ready"
    store.close()
    return path


def make_pipeline(llm, db_path: Path, data_dir: Path = REPO_DATA_DIR, web=None) -> ChatPipeline:
    return ChatPipeline(
        llm,
        sql_store=SQLStore(db_path=db_path, data_dir=data_dir),
        dataset_store=DatasetContextStore(data_dir=data_dir),
        web=web or FakeWeb(),
    )


@pytest.fixture
def pipeline_factory():
    created: list[ChatPipeline] = []

    def factory(llm, db_path, data_dir=REPO_DATA_DIR, web=None):
        p = make_pipeline(llm, db_path, data_dir, web)
        created.append(p)
        return p

    yield factory
    for p in created:
        p.sql_store.close()


@pytest.fixture
def csv_dir_without(tmp_path):
    """Copy the 12 source CSVs into tmp_path/csv, omitting the given file names."""

    def factory(*omit: str) -> Path:
        target = tmp_path / "csv"
        target.mkdir(exist_ok=True)
        for csv_file in CSV_TABLES:
            if csv_file not in omit:
                shutil.copy(REPO_DATA_DIR / csv_file, target / csv_file)
        return target

    return factory
