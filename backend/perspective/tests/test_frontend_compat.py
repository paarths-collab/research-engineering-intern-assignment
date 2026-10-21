"""Backend side of the frontend/perspective response contract."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from perspective.models.schemas import PerspectiveGraphEdge, PerspectiveSimulateRequest
from perspective.routes.perspective_routes import router
from perspective.services.simulator_service import PerspectiveSimulatorService


def _simulate(payload):
    return PerspectiveSimulatorService().simulate(PerspectiveSimulateRequest(**payload)).model_dump()


def _node(result, node_id):
    return next(n for n in result["nodes"] if n["id"] == node_id)


# --- 1. ideology distance key ------------------------------------------------

def test_debate_node_emits_both_distance_keys(payload):
    data = _node(_simulate(payload), "debate-n1")["data"]

    assert "ideologicalDistance" in data
    assert "ideology_distance" in data
    assert data["ideology_distance"] == data["ideologicalDistance"]
    assert 0.0 <= data["ideology_distance"] <= 1.0


def test_discussion_node_emits_both_distance_keys(payload):
    for node in payload["nodes"]:
        if node["id"] == "d1":
            node["type"] = "discussion"
    result = _simulate(payload)
    data = _node(result, "discussion-n1")["data"]

    assert data["ideology_distance"] == data["ideologicalDistance"]


def test_generated_nodes_provide_every_key_frontend_nodes_read(payload):
    result = _simulate(payload)
    debate = _node(result, "debate-n1")["data"]
    # keys read by DebateNode.jsx / DiscussionNode.jsx
    assert {"label", "summary", "reactions", "rounds", "ideology_distance"} <= set(debate)

    payload["nodes"] = [n for n in payload["nodes"] if n["id"] not in {"d1", "p2"}]
    payload["edges"] = [{"id": "e1", "source": "p1", "target": "n1"}]
    result = _simulate(payload)
    # keys read by AnalysisNode.jsx / NewsNode.jsx
    assert {"label", "summary", "reactions"} <= set(_node(result, "analysis-n1")["data"])
    assert {"label", "description", "analysis_summary"} <= set(_node(result, "n1")["data"])


# --- 2. edge handles ----------------------------------------------------------

def test_request_edge_handles_survive_round_trip(payload):
    payload["edges"][0]["sourceHandle"] = "out"
    payload["edges"][0]["targetHandle"] = "in-left"
    payload["edges"][2]["sourceHandle"] = "out-bottom"

    result = _simulate(payload)
    e1 = next(e for e in result["edges"] if e["id"] == "e1")
    e3 = next(e for e in result["edges"] if e["id"] == "e3")
    e2 = next(e for e in result["edges"] if e["id"] == "e2")

    assert (e1["sourceHandle"], e1["targetHandle"]) == ("out", "in-left")
    assert e3["sourceHandle"] == "out-bottom" and "targetHandle" not in e3
    assert "sourceHandle" not in e2 and "targetHandle" not in e2


def test_route_omits_absent_handles_and_keeps_present_ones(payload):
    payload["edges"][0]["sourceHandle"] = "out"
    app = FastAPI()
    app.include_router(router)
    body = TestClient(app).post("/simulate", json=payload).json()

    e1 = next(e for e in body["edges"] if e["id"] == "e1")
    assert e1["sourceHandle"] == "out"
    for edge in body["edges"]:
        if edge["id"] != "e1":
            assert "sourceHandle" not in edge and "targetHandle" not in edge


def test_edge_schema_defaults_are_backward_compatible():
    edge = PerspectiveGraphEdge(id="x", source="a", target="b")
    assert edge.sourceHandle is None and edge.targetHandle is None
    assert "sourceHandle" not in edge.model_dump()


def test_generated_edges_are_well_formed(payload):
    result = _simulate(payload)
    ids = [e["id"] for e in result["edges"]]
    node_ids = {n["id"] for n in result["nodes"]}

    assert len(ids) == len(set(ids))
    pairs = [(e["source"], e["target"]) for e in result["edges"]]
    assert len(pairs) == len(set(pairs))
    for edge in result["edges"]:
        assert edge["source"] in node_ids and edge["target"] in node_ids
        assert edge["type"] == "smoothstep" and edge["animated"] is True


def test_generated_edge_ids_do_not_collide_with_request_edge_ids(payload):
    # A pre-existing edge already uses the id the analysis branch would generate.
    payload["nodes"] = [n for n in payload["nodes"] if n["id"] not in {"d1", "p2"}]
    payload["edges"] = [{"id": "e-p1-analysis-n1", "source": "p1", "target": "n1"}]
    result = _simulate(payload)

    ids = [e["id"] for e in result["edges"]]
    assert len(ids) == len(set(ids))
    assert any(e["source"] == "p1" and e["target"] == "analysis-n1" for e in result["edges"])


# --- 3. connector node identity ------------------------------------------------

def test_generated_connector_node_references_requested_node_and_position(payload):
    for node in payload["nodes"]:
        if node["id"] == "d1":
            node["position"] = {"x": 410.0, "y": 777.0}
    result = _simulate(payload)

    generated = _node(result, "debate-n1")
    assert generated["data"]["connectorId"] == "d1"
    assert generated["data"]["connectorIds"] == ["d1"]
    assert generated["position"] == {"x": 410.0, "y": 777.0}
    # The user's own node is still present, unchanged, with its original id.
    assert _node(result, "d1")["position"] == {"x": 410.0, "y": 777.0}


def test_shared_connector_keeps_default_position(payload):
    # One connector feeding two news nodes is ambiguous: don't stack both outputs on it.
    payload["nodes"].append(
        {"id": "n2", "type": "news", "position": {"x": 900, "y": 50}, "data": {"label": "Second story"}}
    )
    payload["edges"].append({"id": "e4", "source": "d1", "target": "n2"})
    for node in payload["nodes"]:
        if node["id"] == "d1":
            node["position"] = {"x": 410.0, "y": 777.0}
    result = _simulate(payload)

    first, second = _node(result, "debate-n1"), _node(result, "debate-n2")
    assert first["position"] != {"x": 410.0, "y": 777.0}
    assert second["position"] == {"x": 900 + 220.0, "y": 50 + 240.0}
    assert first["data"]["connectorId"] == second["data"]["connectorId"] == "d1"


# --- 4. per-persona fallback ----------------------------------------------------

def test_fallback_reactions_differ_per_persona_without_losing_label(payload):
    result = _simulate(payload)
    reactions = {r["persona"]: r for r in _node(result, "debate-n1")["data"]["reactions"]}

    alice, bob = reactions["Alice"], reactions["Bob"]
    assert alice["reaction"] != bob["reaction"]
    assert "Alice" in alice["reaction"] and "Bob" not in alice["reaction"]
    assert "cautious" in alice["reaction"] and "bold" in bob["reaction"]
    for r in (alice, bob):
        assert r["generation"] == "fallback_template"
        assert r["fallback_reason"] == "missing_key"


def test_fallback_only_uses_supplied_persona_fields(payload):
    for node in payload["nodes"]:
        if node["id"] == "p1":
            node["data"].pop("description")
    text = next(
        r["reaction"] for r in _node(_simulate(payload), "debate-n1")["data"]["reactions"] if r["persona"] == "Alice"
    )
    assert "The lens I was given" not in text  # no description -> nothing invented


def test_fallback_truncates_very_long_persona_prompt(payload):
    for node in payload["nodes"]:
        if node["id"] == "p1":
            node["data"]["description"] = "word " * 500
    text = next(
        r["reaction"] for r in _node(_simulate(payload), "debate-n1")["data"]["reactions"] if r["persona"] == "Alice"
    )
    assert len(text) < 2500
    assert "..." in text
