import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from perspective.models.schemas import PerspectiveSimulateRequest
from perspective.routes.perspective_routes import router
from perspective.services import simulator_service
from perspective.services.simulator_service import PerspectiveSimulatorService

from .conftest import make_fake_client


def _simulate(payload):
    return PerspectiveSimulatorService().simulate(PerspectiveSimulateRequest(**payload)).model_dump()


def _generated_node(result):
    return next(n for n in result["nodes"] if n["id"] == "debate-n1")


def _assert_rounds_are_template(rounds):
    assert rounds
    for rnd in rounds:
        assert rnd["generation"] == "template"
        assert rnd["simulated"] is True
        assert rnd["turns"]
        for turn in rnd["turns"]:
            assert turn["generation"] == "template"
            assert turn["simulated"] is True


def test_no_key_everything_labelled_fallback_and_template(payload):
    result = _simulate(payload)

    assert result["simulated"] is True
    assert "not observed community data" in result["simulation_notice"]
    assert "validated forecast" in result["simulation_notice"]
    assert result["generation"] == {
        "reactions": {"llm": 0, "fallback_template": 2},
        "rounds": "template",
        "model": None,
    }

    node = _generated_node(result)
    assert node["data"]["simulated"] is True
    assert node["data"]["generation"]["reactions"]["fallback_template"] == 2
    assert len(node["data"]["reactions"]) == 2
    for reaction in node["data"]["reactions"]:
        assert reaction["generation"] == "fallback_template"
        assert reaction["fallback_reason"] == "missing_key"
        assert "model" not in reaction
        assert reaction["reaction"]  # prose itself is unchanged and present
    _assert_rounds_are_template(node["data"]["rounds"])

    # Existing keys are preserved.
    assert result["result_type"] == "debate"
    assert {"news_id", "outcome", "persona_count", "distance"} <= set(result["generated"][0])
    assert set(node["data"]["reactions"][0]) >= {"personaId", "persona", "mode", "reaction"}
    assert set(node["data"]["rounds"][0]["turns"][0]) >= {"persona", "target", "question", "answer", "text"}


def test_llm_stub_labels_reactions_llm_but_rounds_stay_template(payload, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("PERSPECTIVE_GROQ_MODEL", "test-model")
    monkeypatch.setattr(simulator_service.httpx, "Client", make_fake_client(content="I think this matters."))

    result = _simulate(payload)

    assert result["simulated"] is True
    assert result["generation"] == {
        "reactions": {"llm": 2, "fallback_template": 0},
        "rounds": "template",
        "model": "test-model",
    }
    node = _generated_node(result)
    for reaction in node["data"]["reactions"]:
        assert reaction["generation"] == "llm"
        assert reaction["model"] == "test-model"
        assert reaction["reaction"] == "I think this matters."
        assert "fallback_reason" not in reaction
    _assert_rounds_are_template(node["data"]["rounds"])


def test_llm_call_failure_is_labelled_with_reason(payload, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(
        simulator_service.httpx, "Client", make_fake_client(error=httpx.ConnectError("boom"))
    )

    result = _simulate(payload)

    assert result["generation"]["reactions"] == {"llm": 0, "fallback_template": 2}
    assert result["generation"]["model"] is None
    for reaction in _generated_node(result)["data"]["reactions"]:
        assert reaction["generation"] == "fallback_template"
        assert reaction["fallback_reason"] == "error"


def test_empty_llm_content_is_labelled_with_reason(payload, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(simulator_service.httpx, "Client", make_fake_client(content="   "))

    result = _simulate(payload)

    for reaction in _generated_node(result)["data"]["reactions"]:
        assert reaction["generation"] == "fallback_template"
        assert reaction["fallback_reason"] == "empty"


def test_analysis_node_and_news_node_carry_labels(payload):
    payload["nodes"] = [n for n in payload["nodes"] if n["id"] != "d1" and n["id"] != "p2"]
    payload["edges"] = [{"id": "e1", "source": "p1", "target": "n1"}]

    result = _simulate(payload)

    analysis = next(n for n in result["nodes"] if n["id"] == "analysis-n1")
    news = next(n for n in result["nodes"] if n["id"] == "n1")
    for node in (analysis, news):
        assert node["data"]["simulated"] is True
        assert node["data"]["generation"]["rounds"] == "template"
        assert node["data"]["reactions"][0]["generation"] == "fallback_template"
        _assert_rounds_are_template(node["data"]["rounds"])


def test_route_returns_labels(payload, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("PERSPECTIVE_GROQ_MODEL", "test-model")
    monkeypatch.setattr(simulator_service.httpx, "Client", make_fake_client(content="Stubbed reply"))

    # The controller holds a module-level service; its _fetch_globe_events is patched by conftest.
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post("/simulate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["simulated"] is True
    assert body["simulation_notice"]
    assert body["generation"]["model"] == "test-model"
    node = next(n for n in body["nodes"] if n["id"] == "debate-n1")
    assert all(r["generation"] == "llm" for r in node["data"]["reactions"])
    assert all(r["generation"] == "template" for r in node["data"]["rounds"])


def test_route_fallback_labels_without_key(payload):
    app = FastAPI()
    app.include_router(router)
    body = TestClient(app).post("/simulate", json=payload).json()

    assert body["simulated"] is True
    assert body["generation"]["reactions"] == {"llm": 0, "fallback_template": 2}


def test_legacy_groq_function_still_returns_text():
    text = simulator_service._generate_persona_reaction_via_groq(
        persona_name="Alice",
        persona_traits=[],
        persona_prompt="",
        mode="analysis",
        news_title="T",
        news_summary="",
        reports=[],
    )
    assert isinstance(text, str) and text
