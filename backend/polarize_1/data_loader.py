"""
data_loader.py — Loads and holds all CSV data in memory at startup.

Files expected in ./data/:
    subreddit_domain_flow_v2.csv       — raw linking counts (subreddit, domain, count)
    clean_top_distinctive_domains.csv  — pre-computed lift + category per domain
    echo_chamber_scores.csv            — pre-computed echo score per subreddit
"""

import os
import csv
import pandas as pd
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Dict, List

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


@dataclass
class DomainRow:
    subreddit: str
    domain: str
    count: int
    category: str
    sub_total: int
    domain_total: int
    p_domain_given_sub: float
    p_domain_global: float
    lift: float


@dataclass
class FlowRow:
    subreddit: str
    domain: str
    count: int


@dataclass
class DataStore:
    # Raw flows: subreddit → domain → count
    flow_vectors: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))

    # Full dataframe-like list of flow rows
    flow_df: List[FlowRow] = field(default_factory=list)

    # Distinctive domains: subreddit → [DomainRow, ...]
    distinctive: Dict[str, List[DomainRow]] = field(default_factory=lambda: defaultdict(list))

    # Echo scores: subreddit → lift
    echo_scores: Dict[str, float] = field(default_factory=dict)

    # Global domain → category mapping
    domain_to_category: Dict[str, str] = field(default_factory=dict)

    # Ordered list of subreddits (from flow data)
    subreddits: List[str] = field(default_factory=list)

    # Store the actual posts dataframe
    posts: pd.DataFrame = field(default=None)

    def load(self):
        self._load_flow()
        self._load_distinctive()
        self._load_echo_scores()
        
        # Load subreddits from clean_posts.csv as requested
        posts_path = os.path.join(DATA_DIR, "clean_posts.csv")
        if os.path.exists(posts_path):
            self.posts = pd.read_csv(posts_path)
            if "subreddit" in self.posts.columns:
                self.subreddits = sorted(self.posts["subreddit"].dropna().unique().tolist())
                print(f"Loaded posts: {len(self.posts)}")
                print(f"Detected subreddits: {len(self.subreddits)}")
            else:
                # Fallback to flow_vectors if subreddit column is missing
                self.subreddits = sorted(self.flow_vectors.keys())
        else:
            self.subreddits = sorted(self.flow_vectors.keys())

    # ── Loaders ──────────────────────────────────────────────────────────────

    def _load_flow(self):
        path = os.path.join(DATA_DIR, "subreddit_domain_flow_v2.csv")
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                s, d, c = row["subreddit"], row["domain"], int(row["count"])
                self.flow_vectors[s][d] += c
                self.flow_df.append(FlowRow(subreddit=s, domain=d, count=c))

    def _load_distinctive(self):
        path = os.path.join(DATA_DIR, "clean_top_distinctive_domains.csv")
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                s, d, cat = row["subreddit"], row["domain"], row["category"]
                # Store globally (last one wins, but categorization should be consistent)
                self.domain_to_category[d] = cat
                
                self.distinctive[s].append(
                    DomainRow(
                        subreddit=s,
                        domain=d,
                        count=int(row["count"]),
                        category=cat,
                        sub_total=int(row["sub_total"]),
                        domain_total=int(row["domain_total"]),
                        p_domain_given_sub=float(row["p_domain_given_sub"]),
                        p_domain_global=float(row["p_domain_global"]),
                        lift=float(row["lift"]),
                    )
                )

    def _load_echo_scores(self):
        path = os.path.join(DATA_DIR, "echo_chamber_scores.csv")
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self.echo_scores[row["subreddit"]] = float(row["lift"])
