"""
Tests — Layer 2: Fast Geo Filter
"""
import pytest
from app.pipeline.geo_filter import fast_geo_filter, is_vague, VAGUE_BLOCKLIST
from app.database.models import RawPost
import time


def _make_post(post_id, title, score=500):
    return RawPost(
        id=post_id, title=title, subreddit="worldnews",
        score=score, num_comments=100, created_utc=time.time(),
        engagement_score=score * 0.6 + 40,
    )


class TestVagueTermDetection:
    def test_vague_global(self):
        assert is_vague("global")

    def test_vague_middle_east(self):
        assert is_vague("Middle East")

    def test_vague_europe(self):
        assert is_vague("europe")

    def test_specific_country_not_vague(self):
        assert not is_vague("Iran")

    def test_city_not_vague(self):
        assert not is_vague("Tehran")


class TestGeoFilter:
    def test_pass_specific_country(self):
        posts = [_make_post("p1", "Iran launches military exercise near Strait of Hormuz")]
        result = fast_geo_filter(posts)
        assert len(result) == 1
        assert result[0].post_id == "p1"

    def test_pass_city_mention(self):
        posts = [_make_post("p1", "Explosion reported in Kyiv downtown area")]
        result = fast_geo_filter(posts)
        assert len(result) == 1

    def test_drop_vague_only(self):
        posts = [_make_post("p1", "Global markets react to international trade news")]
        result = fast_geo_filter(posts)
        assert len(result) == 0

    def test_drop_abstract_regional(self):
        posts = [_make_post("p1", "Middle East tensions escalate amid regional conflict")]
        result = fast_geo_filter(posts)
        assert len(result) == 0

    def test_pass_abbreviation_us(self):
        posts = [_make_post("p1", "US imposes new sanctions on Russia over invasion")]
        result = fast_geo_filter(posts)
        assert len(result) == 1

    def test_multiple_countries(self):
        posts = [_make_post("p1", "India and Pakistan clash at Line of Control")]
        result = fast_geo_filter(posts)
        assert len(result) == 1
        assert len(result[0].detected_geo_terms) >= 2

    def test_mixed_batch(self, sample_posts):
        # 3 of 4 sample posts have geo mentions (last one is global/vague)
        result = fast_geo_filter(sample_posts)
        assert len(result) >= 2  # At least Iran/Israel and Russia/Ukraine posts pass

    def test_empty_input(self):
        result = fast_geo_filter([])
        assert result == []

    def test_detected_terms_populated(self):
        posts = [_make_post("p1", "Syria and Turkey engage in border skirmish")]
        result = fast_geo_filter(posts)
        assert len(result) == 1
        assert len(result[0].detected_geo_terms) >= 1
