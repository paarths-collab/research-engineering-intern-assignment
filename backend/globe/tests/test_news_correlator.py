"""
Tests — Layer 5: News Correlation
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.pipeline.news_correlator import _is_trusted, _article_id, correlate_news_for_event
from app.database.models import StructuredEvent, NewsBundle
import httpx


class TestTrustedDomains:
    def test_reuters_trusted(self):
        assert _is_trusted("https://reuters.com/world/iran-attack-2024")

    def test_bbc_trusted(self):
        assert _is_trusted("https://bbc.com/news/world-12345")

    def test_unknown_source_not_trusted(self):
        assert not _is_trusted("https://randomnewsblog.net/article/123")

    def test_apnews_trusted(self):
        assert _is_trusted("https://apnews.com/article/iran-israel")


class TestArticleId:
    def test_same_inputs_same_id(self):
        id1 = _article_id("https://reuters.com/test", "event-001")
        id2 = _article_id("https://reuters.com/test", "event-001")
        assert id1 == id2

    def test_different_url_different_id(self):
        id1 = _article_id("https://reuters.com/test1", "event-001")
        id2 = _article_id("https://reuters.com/test2", "event-001")
        assert id1 != id2

    def test_id_length_16(self):
        art_id = _article_id("https://reuters.com/test", "event-001")
        assert len(art_id) == 16


class TestCorrelateNewsForEvent:
    @pytest.mark.asyncio
    async def test_no_api_keys_returns_empty_bundle(self, sample_events):
        event = sample_events[0]
        with patch("app.pipeline.news_correlator.settings") as mock_settings:
            mock_settings.TAVILY_API_KEY = ""
            mock_settings.NEWSAPI_KEY = ""
            mock_settings.GNEWS_KEY = ""
            mock_settings.NEWSDATA_KEY = ""
            mock_settings.NEWS_ARTICLE_LIMIT = 7
            mock_settings.NEWS_TIME_WINDOW_HOURS = 48

            async with httpx.AsyncClient() as client:
                bundle = await correlate_news_for_event(event, client)

            assert isinstance(bundle, NewsBundle)
            assert bundle.event_id == event.id
            assert bundle.news_count == 0

    @pytest.mark.asyncio
    async def test_deduplication(self, sample_events):
        """Duplicate URLs should be deduplicated."""
        event = sample_events[0]
        duplicate_url = "https://reuters.com/duplicate"

        mock_articles = [
            {"title": "Article 1", "url": duplicate_url, "snippet": "text",
             "source": "reuters.com", "published_at": "2024-01-01"},
            {"title": "Article 2", "url": duplicate_url, "snippet": "text",
             "source": "reuters.com", "published_at": "2024-01-01"},
        ]

        with patch("app.pipeline.news_correlator._search_tavily", return_value=mock_articles), \
             patch("app.pipeline.news_correlator.settings") as mock_settings:
            mock_settings.TAVILY_API_KEY = "fake_key"
            mock_settings.NEWSAPI_KEY = ""
            mock_settings.GNEWS_KEY = ""
            mock_settings.NEWSDATA_KEY = ""
            mock_settings.NEWS_ARTICLE_LIMIT = 7
            mock_settings.NEWS_TIME_WINDOW_HOURS = 48

            async with httpx.AsyncClient() as client:
                bundle = await correlate_news_for_event(event, client)

            assert bundle.news_count == 1  # Deduplicated
