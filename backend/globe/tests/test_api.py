"""
Tests — API Endpoints
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    with patch("app.database.connection.init_db"), \
         patch("app.database.connection.close_db"):
        from app.main import app
        return TestClient(app)


class TestHealthEndpoints:
    def test_health_ok(self, client):
        response = client.get("/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_root_returns_app_info(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "app" in data
        assert "endpoints" in data


class TestEventsEndpoints:
    def test_events_no_data_returns_404(self, client):
        with patch("app.api.routes.events.load_latest_output", return_value=None):
            response = client.get("/events/")
            assert response.status_code == 404

    def test_events_returns_data(self, client):
        mock_data = {
            "generated_at": "2024-01-01T00:00:00Z",
            "events": [
                {
                    "id": "cluster-001",
                    "title": "Tehran, Iran — Escalating",
                    "impact_score": 0.72,
                    "risk_level": "High",
                    "sentiment": "negative",
                    "confidence": "High",
                    "locations": [{"name": "Tehran, Iran", "lat": 35.68, "lon": 51.38}],
                    "strategic_implications": ["Implication 1"],
                }
            ],
        }
        with patch("app.api.routes.events.load_latest_output", return_value=mock_data):
            response = client.get("/events/")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1

    def test_events_filter_by_risk(self, client):
        mock_data = {
            "generated_at": "2024-01-01T00:00:00Z",
            "events": [
                {"id": "1", "risk_level": "High", "impact_score": 0.8, "confidence": "High",
                 "title": "T1", "sentiment": "neg", "locations": [], "strategic_implications": []},
                {"id": "2", "risk_level": "Low", "impact_score": 0.2, "confidence": "Low",
                 "title": "T2", "sentiment": "neu", "locations": [], "strategic_implications": []},
            ],
        }
        with patch("app.api.routes.events.load_latest_output", return_value=mock_data):
            response = client.get("/events/?risk_level=High")
            data = response.json()
            assert all(e["risk_level"] == "High" for e in data["events"])

    def test_map_endpoint(self, client):
        mock_data = {
            "generated_at": "2024-01-01T00:00:00Z",
            "events": [
                {
                    "id": "c1", "title": "Test", "impact_score": 0.5,
                    "risk_level": "Medium", "sentiment": "neutral",
                    "confidence": "Medium", "strategic_implications": [],
                    "locations": [{"name": "Moscow, Russia", "lat": 55.75, "lon": 37.61}],
                }
            ],
        }
        with patch("app.api.routes.events.load_latest_output", return_value=mock_data):
            response = client.get("/events/map")
            assert response.status_code == 200
            data = response.json()
            assert "pins" in data
            assert data["pin_count"] >= 1

    def test_summary_endpoint(self, client):
        mock_data = {
            "run_id": "test-001",
            "generated_at": "2024-01-01T00:00:00Z",
            "events": [
                {"risk_level": "High", "sentiment": "negative", "impact_score": 0.7},
                {"risk_level": "Low", "sentiment": "neutral", "impact_score": 0.2},
            ],
        }
        with patch("app.api.routes.events.load_latest_output", return_value=mock_data):
            response = client.get("/events/summary")
            assert response.status_code == 200
            data = response.json()
            assert "risk_distribution" in data
            assert "total_events" in data


class TestPipelineEndpoints:
    def test_pipeline_status_idle(self, client):
        with patch("app.api.routes.pipeline.get_current_status", return_value=None):
            response = client.get("/pipeline/status")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "idle"

    def test_pipeline_trigger(self, client):
        with patch("app.api.routes.pipeline._pipeline_lock") as mock_lock:
            mock_lock.locked.return_value = False
            response = client.post("/pipeline/run")
            assert response.status_code == 200
