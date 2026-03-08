"""
Tests — Layer 8: Event Clustering
"""
import pytest
from unittest.mock import patch
from app.pipeline.clustering import (
    _dominant_sentiment, _escalation_level, _location_key, cluster_events
)
from app.database.models import ResolvedLocation, NewsBundle


class TestHelpers:
    def test_dominant_sentiment_negative(self):
        assert _dominant_sentiment(["negative", "negative", "neutral"]) == "negative"

    def test_dominant_sentiment_empty(self):
        assert _dominant_sentiment([]) == "neutral"

    def test_escalation_high_risk(self):
        assert _escalation_level(0.3, "High") == "Escalating"

    def test_escalation_high_impact(self):
        assert _escalation_level(0.7, "Low") == "Escalating"

    def test_escalation_medium(self):
        assert _escalation_level(0.4, "Medium") == "Active"

    def test_escalation_emerging(self):
        assert _escalation_level(0.1, "Low") == "Emerging"

    def test_location_key_city_country(self):
        assert _location_key("Tehran, Iran") == "tehran"

    def test_location_key_country_only(self):
        assert _location_key("Russia") == "russia"


class TestClusterEvents:
    def test_cluster_returns_list(self, sample_events, sample_posts, sample_bundles, sample_intel):
        from app.pipeline.impact_scorer import score_all_events
        posts_map = {p.id: p for p in sample_posts}
        bundles_map = {b.event_id: b for b in sample_bundles}
        intel_map = {i.event_id: i for i in sample_intel}
        scores = score_all_events(sample_events, posts_map, bundles_map, intel_map)
        scores_map = {s.event_id: s for s in scores}
        geo_map = {
            "Tehran, Iran": ResolvedLocation(name="Tehran, Iran", lat=35.68, lon=51.38),
            "Moscow, Russia": ResolvedLocation(name="Moscow, Russia", lat=55.75, lon=37.61),
        }

        with patch("app.pipeline.clustering._persist_clusters"):
            clusters = cluster_events(
                sample_events, geo_map, posts_map, intel_map, scores_map, bundles_map
            )

        assert isinstance(clusters, list)
        assert len(clusters) >= 1

    def test_clusters_sorted_by_impact(self, sample_events, sample_posts, sample_bundles, sample_intel):
        from app.pipeline.impact_scorer import score_all_events
        posts_map = {p.id: p for p in sample_posts}
        bundles_map = {b.event_id: b for b in sample_bundles}
        intel_map = {i.event_id: i for i in sample_intel}
        scores = score_all_events(sample_events, posts_map, bundles_map, intel_map)
        scores_map = {s.event_id: s for s in scores}
        geo_map = {
            "Tehran, Iran": ResolvedLocation(name="Tehran, Iran", lat=35.68, lon=51.38),
            "Moscow, Russia": ResolvedLocation(name="Moscow, Russia", lat=55.75, lon=37.61),
        }

        with patch("app.pipeline.clustering._persist_clusters"):
            clusters = cluster_events(
                sample_events, geo_map, posts_map, intel_map, scores_map, bundles_map
            )

        impacts = [c.average_impact for c in clusters]
        assert impacts == sorted(impacts, reverse=True)

    def test_empty_events_returns_empty(self):
        with patch("app.pipeline.clustering._persist_clusters"):
            clusters = cluster_events({}, {}, {}, {}, {}, {})
        assert clusters == []
