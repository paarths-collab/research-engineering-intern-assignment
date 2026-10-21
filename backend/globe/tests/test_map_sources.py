"""
Regression tests: map events must only carry news sources from their own
cluster (post_id -> StructuredEvent.id -> NewsBundle.event_id).
"""
import json
from pathlib import Path
from types import SimpleNamespace

from app.database.models import (
    RawPost, GeoCandidate, ResolvedLocation, StructuredEvent,
    NewsBundle, NewsArticle, NarrativeIntel, ImpactScore, EventCluster,
)
from app.pipeline import orchestrator
from app.pipeline.orchestrator import _build_map_events, run_pipeline


def _post(post_id: str, title: str, engagement: float = 1000.0) -> RawPost:
    return RawPost(
        id=post_id,
        title=title,
        subreddit="worldnews",
        score=100,
        num_comments=10,
        created_utc=1700000000.0,
        engagement_score=engagement,
    )


def _event(event_id: str, post_id: str, location: str) -> StructuredEvent:
    return StructuredEvent(id=event_id, post_id=post_id, primary_location=location)


def _bundle(event_id: str, urls: list[str]) -> NewsBundle:
    articles = [
        NewsArticle(
            id=f"{event_id}-{i}",
            event_id=event_id,
            title=f"Article {url}",
            url=url,
            source="example.test",
            is_trusted=True,
        )
        for i, url in enumerate(urls)
    ]
    return NewsBundle(
        event_id=event_id,
        articles=articles,
        news_count=len(articles),
        trusted_source_count=len(articles),
    )


def _cluster(cluster_id: str, post_ids: list[str], location: str) -> EventCluster:
    return EventCluster(
        cluster_id=cluster_id,
        post_ids=post_ids,
        primary_location=location,
        lat=1.0,
        lon=2.0,
    )


A_URL = "https://alpha.test/story-a"
B_URL = "https://beta.test/story-b"


class TestBuildMapEventsSources:
    def test_each_cluster_gets_only_its_own_sources(self):
        posts_map = {
            "p-a": _post("p-a", "Alpha thing happens"),
            "p-b": _post("p-b", "Beta thing happens"),
            "p-c": _post("p-c", "Gamma thing happens"),
        }
        events = [
            _event("e-a", "p-a", "Alphaville"),
            _event("e-b", "p-b", "Betaburg"),
            _event("e-c", "p-c", "Gammaton"),
        ]
        bundles_map = {
            "e-a": _bundle("e-a", [A_URL]),
            "e-b": _bundle("e-b", [B_URL]),
        }
        clusters = [
            _cluster("c-a", ["p-a"], "Alphaville"),
            _cluster("c-b", ["p-b"], "Betaburg"),
            _cluster("c-c", ["p-c"], "Gammaton"),
        ]

        result = {m.id: m for m in _build_map_events(clusters, posts_map, bundles_map, events)}

        assert [s["url"] for s in result["c-a"].news_sources] == [A_URL]
        assert [s["url"] for s in result["c-b"].news_sources] == [B_URL]
        # No bundle for this cluster: empty, never another cluster's sources
        assert result["c-c"].news_sources == []

    def test_cluster_with_event_but_no_bundle_stays_empty_even_if_others_have_news(self):
        posts_map = {"p-a": _post("p-a", "Alpha"), "p-b": _post("p-b", "Beta")}
        events = [_event("e-a", "p-a", "Alphaville"), _event("e-b", "p-b", "Betaburg")]
        bundles_map = {"e-b": _bundle("e-b", [B_URL])}
        clusters = [_cluster("c-a", ["p-a"], "Alphaville")]

        (m,) = _build_map_events(clusters, posts_map, bundles_map, events)

        assert m.news_sources == []

    def test_unknown_post_ids_yield_no_sources(self):
        # Cluster references a post that no event maps to
        posts_map = {"p-x": _post("p-x", "Orphan")}
        bundles_map = {"e-b": _bundle("e-b", [B_URL])}
        clusters = [_cluster("c-x", ["p-x"], "Nowhere")]

        (m,) = _build_map_events(clusters, posts_map, bundles_map, [])

        assert m.news_sources == []

    def test_dedup_and_cap_of_five_within_a_cluster(self):
        # One cluster, three posts/events. Bundles overlap on one URL and
        # contain more than five distinct articles in total.
        urls_1 = [f"https://big.test/{n}" for n in (1, 2, 3)]
        urls_2 = [f"https://big.test/{n}" for n in (3, 4, 5)]  # 3 duplicates
        urls_3 = [f"https://big.test/{n}" for n in (6, 7, 8)]
        posts_map = {pid: _post(pid, f"Big {pid}") for pid in ("p1", "p2", "p3", "p-o")}
        events = [
            _event("e1", "p1", "Bigcity"),
            _event("e2", "p2", "Bigcity"),
            _event("e3", "p3", "Bigcity"),
            _event("e-o", "p-o", "Othertown"),
        ]
        bundles_map = {
            "e1": _bundle("e1", urls_1),
            "e2": _bundle("e2", urls_2),
            "e3": _bundle("e3", urls_3),
            "e-o": _bundle("e-o", [B_URL]),
        }
        clusters = [
            _cluster("c-big", ["p1", "p2", "p3"], "Bigcity"),
            _cluster("c-o", ["p-o"], "Othertown"),
        ]

        result = {m.id: m for m in _build_map_events(clusters, posts_map, bundles_map, events)}

        big_urls = [s["url"] for s in result["c-big"].news_sources]
        assert big_urls == [f"https://big.test/{n}" for n in (1, 2, 3, 4, 5)]
        assert len(big_urls) == len(set(big_urls)) == 5
        assert [s["url"] for s in result["c-o"].news_sources] == [B_URL]

    def test_source_dict_shape_is_unchanged(self):
        posts_map = {"p-a": _post("p-a", "Alpha")}
        events = [_event("e-a", "p-a", "Alphaville")]
        bundles_map = {"e-a": _bundle("e-a", [A_URL])}
        clusters = [_cluster("c-a", ["p-a"], "Alphaville")]

        (m,) = _build_map_events(clusters, posts_map, bundles_map, events)

        assert m.news_sources == [
            {"title": f"Article {A_URL}", "url": A_URL, "source": "example.test", "trusted": True}
        ]


class TestRunPipelineSources:
    async def test_saved_map_events_have_per_cluster_sources(self, monkeypatch, tmp_path):
        posts = [
            _post("p-a", "Alpha thing happens"),
            _post("p-b", "Beta thing happens"),
            _post("p-c", "Gamma thing happens"),
        ]
        candidates = [GeoCandidate(post_id=p.id, title=p.title) for p in posts]
        locations = {
            "p-a": ResolvedLocation(name="Alphaville", lat=10.0, lon=10.0),
            "p-b": ResolvedLocation(name="Betaburg", lat=20.0, lon=20.0),
            "p-c": ResolvedLocation(name="Gammaton", lat=30.0, lon=30.0),
        }
        pairs = [(c, locations[c.post_id]) for c in candidates]
        events = [
            _event("e-a", "p-a", "Alphaville"),
            _event("e-b", "p-b", "Betaburg"),
            _event("e-c", "p-c", "Gammaton"),
        ]
        # Bundle order deliberately puts beta first so a global scan would
        # hand its URL to every cluster.
        bundles = [_bundle("e-b", [B_URL]), _bundle("e-a", [A_URL])]
        intel = [
            NarrativeIntel(event_id=e.id, summary=f"Summary for {e.id}") for e in events
        ]
        scores = [ImpactScore(event_id=e.id, impact_value=0.5) for e in events]

        async def fake_fetch_reddit_posts():
            return posts

        async def fake_resolve(_candidates):
            return pairs

        async def fake_structure(_pairs):
            return events

        async def fake_correlate(_events):
            return bundles

        async def fake_analyse(_posts_map, _events, _bundles_map):
            return intel

        monkeypatch.setattr(orchestrator, "fetch_reddit_posts", fake_fetch_reddit_posts)
        monkeypatch.setattr(orchestrator, "persist_raw_posts", lambda _posts: None)
        monkeypatch.setattr(orchestrator, "fast_geo_filter", lambda _posts: candidates)
        monkeypatch.setattr(orchestrator, "resolve_all_candidates", fake_resolve)
        monkeypatch.setattr(orchestrator, "structure_all_events", fake_structure)
        monkeypatch.setattr(orchestrator, "correlate_all_events", fake_correlate)
        monkeypatch.setattr(orchestrator, "analyse_all_events", fake_analyse)
        monkeypatch.setattr(orchestrator, "score_all_events", lambda *_a, **_k: scores)
        monkeypatch.setattr("app.pipeline.clustering._persist_clusters", lambda _clusters: None)
        monkeypatch.setattr(
            orchestrator, "get_settings", lambda: SimpleNamespace(DATA_DIR=str(tmp_path))
        )

        status = await run_pipeline(run_id="test-run")

        assert status.status == "complete", status.error
        saved = list(Path(tmp_path).glob("global_events_*.json"))
        assert len(saved) == 1
        payload = json.loads(saved[0].read_text())
        by_location = {
            ev["locations"][0]["name"]: [s["url"] for s in ev["news_sources"]]
            for ev in payload["events"]
        }
        assert by_location == {
            "Alphaville": [A_URL],
            "Betaburg": [B_URL],
            "Gammaton": [],
        }
