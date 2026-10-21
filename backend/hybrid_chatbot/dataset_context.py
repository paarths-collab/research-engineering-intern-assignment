"""
hybrid_chatbot/dataset_context.py
--------------------------------
Lightweight dataset-grounding retriever for chatbot responses.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from .config import DATA_DIR


@dataclass
class DatasetSnippet:
    text: str
    source: str
    metadata: dict
    tokens: set[str]
    # Provenance: stable key of the source row (natural id, else "row:<csv row index>"),
    # 0-based data-row index in the CSV, and the row's date (YYYY-MM-DD) when it has one.
    row_key: str = ""
    row_index: int = -1
    date: Optional[str] = None


class DatasetContextStore:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self._snippets: list[DatasetSnippet] = []
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        self._snippets = []
        self._load_narrative_registry()
        self._load_narrative_intel()
        self._load_subreddit_intel()
        self._load_echo_scores()
        self._load_author_influence()
        self._load_daily_volume()
        self._load_domain_flow()
        self._loaded = True

    def search(self, query: str, top_k: int = 8) -> list[dict]:
        self.load()
        q_tokens = _tokens(query)
        if not q_tokens:
            return []

        scored: list[tuple[float, DatasetSnippet]] = []
        q_lower = query.lower()
        for snip in self._snippets:
            overlap = len(q_tokens & snip.tokens)
            if overlap == 0:
                continue
            score = overlap / max(len(q_tokens), 1)
            narrative_id = str(snip.metadata.get("narrative_id", "")).lower()
            subreddit = str(snip.metadata.get("subreddit", "")).lower()
            if narrative_id and narrative_id in q_lower:
                score += 0.3
            if subreddit and subreddit in q_lower:
                score += 0.2
            scored.append((score, snip))

        # Stable sort: ties keep load order, so results are deterministic.
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, snip in scored[:top_k]:
            out.append(
                {
                    "text": snip.text,
                    "score": round(score, 3),
                    "source": snip.source,
                    "table": snip.source,
                    "row_key": snip.row_key,
                    "row_index": snip.row_index,
                    "date": snip.date,
                    "metadata": {
                        **{k: (None if _is_missing(v) else v) for k, v in snip.metadata.items()},
                        "row_key": snip.row_key,
                        "row_index": snip.row_index,
                        "date": snip.date,
                    },
                }
            )
        return out

    def summary(self) -> str:
        self.load()
        sources = sorted({s.source for s in self._snippets})
        return (
            f"Dataset grounding is built from {len(self._snippets)} indexed records across "
            f"{len(sources)} sources: {', '.join(sources)}."
        )

    # ── Loaders ──────────────────────────────────────────────────────────────
    def _load_narrative_registry(self) -> None:
        path = self.data_dir / "narrative_registry.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        df = _top(df, "total_posts", 400)
        for idx, r in _rows(df):
            text = (
                f"Narrative {_t(r.get('narrative_id'))} uses domain {_t(r.get('primary_domain'))}. "
                f"Representative title: {_t(r.get('representative_title'))}. "
                f"Total posts: {_t(r.get('total_posts'))}, unique subreddits: {_t(r.get('unique_subreddits'))}, "
                f"first seen: {_t(r.get('first_seen'))}."
            )
            self._append(
                text,
                "narrative_registry",
                {"narrative_id": r.get("narrative_id"), "domain": r.get("primary_domain")},
                idx,
                key=r.get("narrative_id"),
                day=r.get("first_seen"),
            )

    def _load_narrative_intel(self) -> None:
        path = self.data_dir / "narrative_intelligence_summary.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        if "spread_strength" in df.columns:
            df = _top(df, "spread_strength", 400)
        for idx, r in _rows(df):
            text = (
                f"Narrative {_t(r.get('narrative_id'))} spread strength is {_t(r.get('spread_strength'))}, "
                f"primary domain {_t(r.get('primary_domain'))}, first seen {_t(r.get('first_seen_x'))}, "
                f"last seen {_t(r.get('last_seen'))}, unique authors {_t(r.get('unique_authors'))}."
            )
            self._append(
                text,
                "narrative_intelligence_summary",
                {
                    "narrative_id": r.get("narrative_id"),
                    "domain": r.get("primary_domain"),
                },
                idx,
                key=r.get("narrative_id"),
                day=r.get("first_seen_x"),
            )

    def _load_subreddit_intel(self) -> None:
        path = self.data_dir / "subreddit_intelligence_summary.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        for idx, r in _rows(df):
            text = (
                f"Subreddit {_t(r.get('subreddit'))} has {_t(r.get('unique_narratives'))} unique narratives, "
                f"{_t(r.get('unique_users'))} users, average score {_t(r.get('avg_score'))}, "
                f"and indicative domain {_t(r.get('domain'))} with lift {_t(r.get('lift'))}."
            )
            self._append(
                text,
                "subreddit_intelligence_summary",
                {"subreddit": r.get("subreddit")},
                idx,
                key=r.get("subreddit"),
            )

    def _load_echo_scores(self) -> None:
        path = self.data_dir / "echo_chamber_scores.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        df = _top(df, "lift", 200)
        for idx, r in _rows(df):
            text = f"Subreddit {_t(r.get('subreddit'))} has echo-chamber lift score {_t(r.get('lift'))}."
            self._append(text, "echo_chamber_scores", {"subreddit": r.get("subreddit")}, idx, key=r.get("subreddit"))

    def _load_author_influence(self) -> None:
        path = self.data_dir / "author_influence_profile.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        df = _top(df, "final_influence_score", 250)
        for idx, r in _rows(df):
            text = (
                f"Author {_t(r.get('author'))} influence score is {_t(r.get('final_influence_score'))}, "
                f"posts {_t(r.get('total_posts'))}, narratives transported {_t(r.get('narratives_transported'))}, "
                f"amplification generated {_t(r.get('total_amplification_generated'))}."
            )
            self._append(text, "author_influence_profile", {"author": r.get("author")}, idx, key=r.get("author"))

    def _load_daily_volume(self) -> None:
        path = self.data_dir / "daily_volume_v2.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        df = _top(df, "post_count", 250)
        for idx, r in _rows(df):
            text = f"Daily volume on {_t(r.get('created_datetime'))} is {_t(r.get('post_count'))} posts."
            self._append(
                text,
                "daily_volume_v2",
                {"date": r.get("created_datetime")},
                idx,
                key=r.get("created_datetime"),
                day=r.get("created_datetime"),
            )

    def _load_domain_flow(self) -> None:
        path = self.data_dir / "subreddit_domain_flow_v2.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        df = _top(df, "count", 400)
        for idx, r in _rows(df):
            text = f"Domain {_t(r.get('domain'))} appears {_t(r.get('count'))} times in subreddit {_t(r.get('subreddit'))}."
            # No single natural key (subreddit/domain pairs): key on the CSV row.
            self._append(
                text,
                "subreddit_domain_flow_v2",
                {"subreddit": r.get("subreddit"), "domain": r.get("domain")},
                idx,
            )

    def _append(
        self,
        text: str,
        source: str,
        metadata: Optional[dict] = None,
        row_index: int = -1,
        key: object = None,
        day: object = None,
    ) -> None:
        clean = " ".join(str(text).split()).strip()
        if not clean:
            return
        has_key = key is not None and not pd.isna(key) and str(key).strip() != ""
        self._snippets.append(
            DatasetSnippet(
                text=clean,
                source=source,
                metadata=metadata or {},
                tokens=_tokens(clean),
                row_key=str(key) if has_key else f"row:{row_index}",
                row_index=int(row_index),
                date=_iso_date(day),
            )
        )


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_.-]+", str(text).lower()) if len(t) >= 3}


def _rows(df: pd.DataFrame):
    """(original CSV row index, record) pairs; the index survives sorting/filtering."""
    return zip((int(i) for i in df.index), df.to_dict(orient="records"))


def _top(df: pd.DataFrame, column: str, n: int) -> pd.DataFrame:
    """Top-n rows by `column`, descending. Rows whose value is missing or non-finite are
    dropped: they cannot be ranked and must not surface as the 'highest'."""
    values = pd.to_numeric(df[column], errors="coerce")
    finite = values.map(lambda v: pd.notna(v) and math.isfinite(v))
    return df[finite].assign(**{column: values[finite]}).sort_values(column, ascending=False, kind="stable").head(n)


def _t(value: object) -> object:
    """Render a CSV value in snippet text; missing / non-finite values are stated, not shown as nan."""
    if _is_missing(value) or (isinstance(value, float) and not math.isfinite(value)):
        return "not recorded"
    return value


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _iso_date(value: object) -> Optional[str]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return pd.Timestamp(value).date().isoformat()
    except Exception:
        return None
