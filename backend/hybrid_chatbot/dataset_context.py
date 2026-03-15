"""
hybrid_chatbot/dataset_context.py
--------------------------------
Lightweight dataset-grounding retriever for chatbot responses.
"""

from __future__ import annotations

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

        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, snip in scored[:top_k]:
            out.append(
                {
                    "text": snip.text,
                    "score": round(score, 3),
                    "source": snip.source,
                    "metadata": snip.metadata,
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
        df = df.sort_values("total_posts", ascending=False).head(400)
        for r in df.to_dict(orient="records"):
            text = (
                f"Narrative {r.get('narrative_id')} uses domain {r.get('primary_domain')}. "
                f"Representative title: {r.get('representative_title')}. "
                f"Total posts: {r.get('total_posts')}, unique subreddits: {r.get('unique_subreddits')}, "
                f"first seen: {r.get('first_seen')}."
            )
            self._append(text, "narrative_registry", {"narrative_id": r.get("narrative_id"), "domain": r.get("primary_domain")})

    def _load_narrative_intel(self) -> None:
        path = self.data_dir / "narrative_intelligence_summary.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        if "spread_strength" in df.columns:
            df = df.sort_values("spread_strength", ascending=False).head(400)
        for r in df.to_dict(orient="records"):
            text = (
                f"Narrative {r.get('narrative_id')} spread strength is {r.get('spread_strength')}, "
                f"primary domain {r.get('primary_domain')}, first seen {r.get('first_seen_x')}, "
                f"last seen {r.get('last_seen')}, unique authors {r.get('unique_authors')}."
            )
            self._append(
                text,
                "narrative_intelligence_summary",
                {
                    "narrative_id": r.get("narrative_id"),
                    "domain": r.get("primary_domain"),
                },
            )

    def _load_subreddit_intel(self) -> None:
        path = self.data_dir / "subreddit_intelligence_summary.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        for r in df.to_dict(orient="records"):
            text = (
                f"Subreddit {r.get('subreddit')} has {r.get('unique_narratives')} unique narratives, "
                f"{r.get('unique_users')} users, average score {r.get('avg_score')}, "
                f"and indicative domain {r.get('domain')} with lift {r.get('lift')}."
            )
            self._append(text, "subreddit_intelligence_summary", {"subreddit": r.get("subreddit")})

    def _load_echo_scores(self) -> None:
        path = self.data_dir / "echo_chamber_scores.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        df = df.sort_values("lift", ascending=False).head(200)
        for r in df.to_dict(orient="records"):
            text = f"Subreddit {r.get('subreddit')} has echo-chamber lift score {r.get('lift')}."
            self._append(text, "echo_chamber_scores", {"subreddit": r.get("subreddit")})

    def _load_author_influence(self) -> None:
        path = self.data_dir / "author_influence_profile.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        df = df.sort_values("final_influence_score", ascending=False).head(250)
        for r in df.to_dict(orient="records"):
            text = (
                f"Author {r.get('author')} influence score is {r.get('final_influence_score')}, "
                f"posts {r.get('total_posts')}, narratives transported {r.get('narratives_transported')}, "
                f"amplification generated {r.get('total_amplification_generated')}."
            )
            self._append(text, "author_influence_profile", {"author": r.get("author")})

    def _load_daily_volume(self) -> None:
        path = self.data_dir / "daily_volume_v2.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        df = df.sort_values("post_count", ascending=False).head(250)
        for r in df.to_dict(orient="records"):
            text = f"Daily volume on {r.get('created_datetime')} is {r.get('post_count')} posts."
            self._append(text, "daily_volume_v2", {"date": r.get("created_datetime")})

    def _load_domain_flow(self) -> None:
        path = self.data_dir / "subreddit_domain_flow_v2.csv"
        if not path.exists():
            return
        df = pd.read_csv(path)
        if df.empty:
            return
        df = df.sort_values("count", ascending=False).head(400)
        for r in df.to_dict(orient="records"):
            text = f"Domain {r.get('domain')} appears {r.get('count')} times in subreddit {r.get('subreddit')}."
            self._append(text, "subreddit_domain_flow_v2", {"subreddit": r.get("subreddit"), "domain": r.get("domain")})

    def _append(self, text: str, source: str, metadata: Optional[dict] = None) -> None:
        clean = " ".join(str(text).split()).strip()
        if not clean:
            return
        self._snippets.append(
            DatasetSnippet(
                text=clean,
                source=source,
                metadata=metadata or {},
                tokens=_tokens(clean),
            )
        )


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_.-]+", str(text).lower()) if len(t) >= 3}
