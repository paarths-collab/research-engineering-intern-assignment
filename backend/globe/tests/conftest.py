"""
pytest conftest — shared fixtures for all test modules.
"""
import os
import pytest
import asyncio

# Set test env vars BEFORE importing app modules
os.environ.setdefault("REDDIT_CLIENT_ID", "test_id")
os.environ.setdefault("REDDIT_CLIENT_SECRET", "test_secret")
os.environ.setdefault("GROQ_API_KEY", "test_groq_key")
os.environ.setdefault("DUCKDB_PATH", ":memory:")
os.environ.setdefault("DATA_DIR", "tests/outputs")
os.environ.setdefault("LOG_DIR", "tests/logs")

import os; os.makedirs("tests/outputs", exist_ok=True)
import os; os.makedirs("tests/logs", exist_ok=True)

from app.database.models import (
    RawPost, GeoCandidate, ResolvedLocation, StructuredEvent,
    NewsBundle, NewsArticle, NarrativeIntel, ImpactScore,
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_posts():
    return [
        RawPost(
            id="abc123",
            title="Iran launches drone strike on Israeli military base in northern region",
            subreddit="worldnews",
            score=3200,
            num_comments=850,
            created_utc=1700000000.0,
            author="reporter_01",
            engagement_score=2360.0,
            velocity_score=200.0,
        ),
        RawPost(
            id="def456",
            title="Russia mobilises additional troops near Ukrainian border",
            subreddit="geopolitics",
            score=1800,
            num_comments=420,
            created_utc=1700001000.0,
            author="reporter_02",
            engagement_score=1248.0,
            velocity_score=150.0,
        ),
        RawPost(
            id="ghi789",
            title="Pakistan and India exchange fire along Line of Control",
            subreddit="worldnews",
            score=900,
            num_comments=200,
            created_utc=1700002000.0,
            author="reporter_03",
            engagement_score=620.0,
            velocity_score=80.0,
        ),
        RawPost(
            id="jkl000",
            title="Global markets react to international trade tensions",
            subreddit="news",
            score=500,
            num_comments=100,
            created_utc=1700003000.0,
            author="reporter_04",
            engagement_score=340.0,
            velocity_score=40.0,
        ),
    ]


@pytest.fixture
def sample_geo_candidates():
    return [
        GeoCandidate(
            post_id="abc123",
            title="Iran launches drone strike on Israeli military base in northern region",
            detected_geo_terms=["iran", "israel"],
        ),
        GeoCandidate(
            post_id="def456",
            title="Russia mobilises additional troops near Ukrainian border",
            detected_geo_terms=["russia", "ukraine"],
        ),
    ]


@pytest.fixture
def sample_resolved_pairs():
    return [
        (
            GeoCandidate(
                post_id="abc123",
                title="Iran launches drone strike on Israeli military base",
                detected_geo_terms=["iran"],
            ),
            ResolvedLocation(name="Tehran, Iran", lat=35.6892, lon=51.3890),
        ),
        (
            GeoCandidate(
                post_id="def456",
                title="Russia mobilises troops near Ukrainian border",
                detected_geo_terms=["russia"],
            ),
            ResolvedLocation(name="Moscow, Russia", lat=55.7558, lon=37.6176),
        ),
    ]


@pytest.fixture
def sample_events():
    return [
        StructuredEvent(
            id="event-001",
            post_id="abc123",
            event_type="conflict",
            primary_location="Tehran, Iran",
            secondary_locations=["Tel Aviv, Israel"],
            key_entities=["Iran", "Israel", "IRGC"],
            search_queries=[
                "Iran Israel drone strike 2024",
                "Iran military attack Israel",
                "IRGC strike Israeli base",
            ],
        ),
        StructuredEvent(
            id="event-002",
            post_id="def456",
            event_type="military_movement",
            primary_location="Moscow, Russia",
            secondary_locations=["Kyiv, Ukraine"],
            key_entities=["Russia", "Ukraine", "Putin"],
            search_queries=[
                "Russia Ukraine military mobilisation 2024",
                "Russian troops Ukrainian border",
                "Putin Ukraine war escalation",
            ],
        ),
    ]


@pytest.fixture
def sample_bundles(sample_events):
    return [
        NewsBundle(
            event_id="event-001",
            articles=[
                NewsArticle(
                    id="n001",
                    event_id="event-001",
                    title="Iran launches largest drone attack on Israel",
                    snippet="Iranian forces launched a large-scale drone offensive...",
                    url="https://reuters.com/news/iran-israel-drone-2024",
                    source="reuters.com",
                    is_trusted=True,
                ),
                NewsArticle(
                    id="n002",
                    event_id="event-001",
                    title="Israel intercepts Iranian drones over northern border",
                    snippet="Israeli air defence systems activated after Iranian strike...",
                    url="https://apnews.com/iran-israel-drones",
                    source="apnews.com",
                    is_trusted=True,
                ),
            ],
            news_count=2,
            trusted_source_count=2,
        ),
        NewsBundle(
            event_id="event-002",
            articles=[
                NewsArticle(
                    id="n003",
                    event_id="event-002",
                    title="Russia sends reinforcements to Ukrainian frontier",
                    snippet="Satellite imagery confirms new Russian troop movements...",
                    url="https://bbc.com/news/russia-ukraine-troops",
                    source="bbc.com",
                    is_trusted=True,
                ),
            ],
            news_count=1,
            trusted_source_count=1,
        ),
    ]


@pytest.fixture
def sample_intel(sample_events):
    return [
        NarrativeIntel(
            event_id="event-001",
            summary="Iran executed a significant drone offensive targeting Israeli military infrastructure, marking a direct escalation in hostilities.",
            sentiment_label="negative",
            sentiment_confidence=0.92,
            risk_level="High",
            strategic_implications=[
                "Risk of full-scale conflict between Iran and Israel",
                "Regional allies may be drawn into the conflict",
                "Oil price spike likely if Strait of Hormuz threatened",
            ],
        ),
        NarrativeIntel(
            event_id="event-002",
            summary="Russia's troop build-up signals continued pressure on Ukraine ahead of potential spring offensive.",
            sentiment_label="negative",
            sentiment_confidence=0.78,
            risk_level="High",
            strategic_implications=[
                "Renewed NATO alert posture expected",
                "Further Western arms transfers to Ukraine likely",
            ],
        ),
    ]
