"""Lexical retrieval ignores function words and needs more than one shared content token."""

from __future__ import annotations

import re

from conftest import REPO_DATA_DIR
from hybrid_chatbot.dataset_context import DatasetContextStore, _tokens

REGISTRY_HEADER = "narrative_id,cluster_id,primary_domain,representative_title,total_posts,unique_subreddits,first_seen\n"


def test_tokens_drop_stopwords_and_short_words():
    assert _tokens("What about the best cake for you?") == {"best", "cake"}
    assert _tokens("Who won the world cup in 2022?") == {"won", "world", "cup", "2022"}


def test_stopwords_and_a_single_shared_word_do_not_match(tmp_path):
    (tmp_path / "narrative_registry.csv").write_text(
        REGISTRY_HEADER
        + "1.0_a.com,1,a.com,Birthright citizenship ruling expected,10,2,2025-01-05\n"
        + "2.0_b.com,2,b.com,What about the ruling for the cake,12,3,2025-01-06\n",
        encoding="utf-8",
    )
    hits = DatasetContextStore(data_dir=tmp_path).search("What about the birthright citizenship ruling?")

    # "What about the ... ruling" shares only stopwords plus one content word with the second row.
    assert [h["row_key"] for h in hits] == ["1.0_a.com"]


def test_single_word_and_two_word_questions_still_match(tmp_path):
    (tmp_path / "narrative_registry.csv").write_text(
        REGISTRY_HEADER + "1.0_a.com,1,a.com,Birthright citizenship ruling expected,10,2,2025-01-05\n",
        encoding="utf-8",
    )
    store = DatasetContextStore(data_dir=tmp_path)
    assert store.search("birthright")
    assert store.search("birthright citizenship")
    assert not store.search("birthright cake")  # both words of a two-word question are required


def test_off_topic_questions_return_no_lexical_hits():
    store = DatasetContextStore(data_dir=REPO_DATA_DIR)
    for query in ("What is the best recipe for chocolate cake?", "Who won the world cup in 2022?", "what is the"):
        assert store.search(query) == [], query


def test_birthright_citizenship_hits_share_content_words_not_function_words():
    store = DatasetContextStore(data_dir=REPO_DATA_DIR)
    hits = store.search("What did the Supreme Court decide about birthright citizenship?")
    content = {"supreme", "court", "decide", "birthright", "citizenship"}
    assert hits
    for hit in hits:
        assert len(content & _tokens(hit["text"])) >= 2, hit["text"]
    # the old behaviour ranked records that matched "what", "the" and one content word first
    assert hits[0]["score"] >= hits[-1]["score"]
    assert not re.search(r"\bnan_nan\b", hits[0]["text"])
