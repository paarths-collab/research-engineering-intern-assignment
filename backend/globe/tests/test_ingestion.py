"""
Tests — Layer 1: Ingestion
"""
import time
import pytest
from unittest.mock import MagicMock, patch
from app.pipeline.ingestion import _engagement_score, _velocity_score, persist_raw_posts
from app.database.models import RawPost


class TestEngagementScoring:
    def test_high_engagement(self):
        score = _engagement_score(5000, 1200)
        assert score == pytest.approx(3480.0, abs=1)

    def test_zero_engagement(self):
        assert _engagement_score(0, 0) == 0.0

    def test_score_weighted_more_than_comments(self):
        s1 = _engagement_score(100, 0)
        s2 = _engagement_score(0, 100)
        assert s1 > s2


class TestVelocityScoring:
    def test_recent_post_high_velocity(self):
        now = time.time()
        velocity = _velocity_score(now - 3600, 1000)
        assert velocity > 500

    def test_old_post_low_velocity(self):
        old_time = time.time() - (72 * 3600)
        velocity = _velocity_score(old_time, 100)
        assert velocity < 2


class TestPersistRawPosts:
    def test_persist_empty_list(self):
        persist_raw_posts([])

    def test_persist_sample_posts(self, sample_posts):
        with patch("app.pipeline.ingestion.get_connection") as mock_conn:
            mock_execute = MagicMock()
            mock_conn.return_value.execute = mock_execute
            persist_raw_posts(sample_posts)
            assert mock_execute.call_count == len(sample_posts)


class TestEngagementThreshold:
    def test_low_engagement_post(self):
        low_eng_post = RawPost(
            id="low001", title="Test", subreddit="news",
            score=1, num_comments=1, created_utc=time.time(),
            engagement_score=1.0,
        )
        assert low_eng_post.engagement_score < 50

    def test_all_sample_posts_above_threshold(self, sample_posts):
        for p in sample_posts:
            assert p.engagement_score >= 50
