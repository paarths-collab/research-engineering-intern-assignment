import json

from perspective.models.schemas import PerspectiveGraphNode, PerspectiveSimulateRequest
from perspective.services import simulator_service as simulator

ORIGINAL_FETCH = simulator.PerspectiveSimulatorService._fetch_globe_events


def test_no_unrelated_event_is_used_as_context():
    node = PerspectiveGraphNode(id="n", type="news", position={}, data={
        "label": "Telescope discovers exoplanet", "description": "Astronomy discovery",
    })
    simulator.PerspectiveSimulatorService()._enrich_news_node(node, [{
        "id": "port", "title": "Port strike widens", "summary": "Dockworkers walk out",
    }])
    assert node.data == {"label": "Telescope discovers exoplanet", "description": "Astronomy discovery"}


def test_globe_envelope_provenance_reaches_presets(monkeypatch):
    payload = {"is_mock": True, "data_source": "mock_sample", "data_notice": "Demo only", "events": [
        {"id": "mock-port", "title": "Port strike", "summary": "Dockworkers walk out"},
    ]}
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, *args, **kwargs):
            return self
        def raise_for_status(self):
            pass
        def json(self):
            return payload
    monkeypatch.setattr(simulator.httpx, "Client", Client)
    events = ORIGINAL_FETCH(simulator.PerspectiveSimulatorService())
    preset = simulator._build_presets_from_events(events, 1)[0]
    assert preset["is_mock"] is True and preset["data_source"] == "mock_sample"
    assert preset["data_notice"] == "Demo only"


def test_old_cached_mock_events_keep_their_source(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"entry": {
        "event_id": "mock-port",
        "news_context": {"articles": [{"title": "Demo headline", "link": "https://example.test/a"}]},
    }}))
    preset = simulator._load_cached_news_presets(cache_path=cache)[0]
    assert preset["data_source"] == "mock_sample" and preset["is_mock"] is True


def test_generated_connectors_do_not_become_inputs_on_repeat(payload):
    service = simulator.PerspectiveSimulatorService()
    payload["nodes"].append({"id": "n2", "type": "news", "position": {}, "data": {"label": "Second story"}})
    payload["edges"].append({"id": "e4", "source": "d1", "target": "n2"})
    first = service.simulate(PerspectiveSimulateRequest(**payload))
    second = service.simulate(PerspectiveSimulateRequest(nodes=first.nodes, edges=first.edges))
    assert [node.id for node in second.nodes] == [node.id for node in first.nodes]
    assert len({node.id for node in second.nodes}) == len(second.nodes)
    assert len(second.edges) == len(first.edges)


def test_repeated_simulation_does_not_accumulate_or_reuse_enrichment(payload, monkeypatch):
    events = [{"id": "mock-port", "title": "Port strike", "summary": "Dockworkers walk out", "is_mock": True}]
    service = simulator.PerspectiveSimulatorService()
    monkeypatch.setattr(service, "_fetch_globe_events", lambda **kwargs: events)
    first = service.simulate(PerspectiveSimulateRequest(**payload))
    news = next(n for n in first.nodes if n.id == "n1")
    assert news.data["globe_context_is_mock"] is True
    monkeypatch.setattr(service, "_fetch_globe_events", lambda **kwargs: [])
    second = service.simulate(PerspectiveSimulateRequest(nodes=first.nodes, edges=first.edges))
    news = next(n for n in second.nodes if n.id == "n1")
    assert news.data["description"] == "Dockworkers extend walkout."
    assert "globe_events" not in news.data


def test_graph_budget_rejects_expansion_before_context_or_provider(monkeypatch):
    import pytest
    from fastapi import HTTPException

    def forbidden(*args, **kwargs):
        raise AssertionError("No lookup or provider call is allowed before admission")
    monkeypatch.setattr(simulator.PerspectiveSimulatorService, "_fetch_globe_events", forbidden)
    monkeypatch.setattr(simulator, "_build_persona_reactions", forbidden)
    personas = [{"id": f"p{i}", "type": "persona", "position": {}, "data": {}} for i in range(8)]
    news = [{"id": f"n{i}", "type": "news", "position": {}, "data": {}} for i in range(2)]
    edges = [{"id": f"{p['id']}-{n['id']}", "source": p['id'], "target": n['id']} for p in personas for n in news]
    service = simulator.PerspectiveSimulatorService()
    with pytest.raises(HTTPException, match="12 persona reactions") as exc:
        service.simulate(PerspectiveSimulateRequest(nodes=personas + news, edges=edges))
    assert exc.value.status_code == 422


def test_round_budget_rejects_before_context_or_provider(payload, monkeypatch):
    import pytest
    from fastapi import HTTPException
    def forbidden(*args, **kwargs): raise AssertionError("No context lookup before work validation")
    monkeypatch.setattr(simulator.PerspectiveSimulatorService, "_fetch_globe_events", forbidden)
    # Two connected personas x 20 rounds x four stories = 160 generated turns.
    for i in range(2, 5):
        payload["nodes"].append({"id": f"n{i}", "type": "news", "position": {}, "data": {}})
        payload["edges"].append({"id": f"story-{i}", "source": "d1", "target": f"n{i}"})
    payload["debate_rounds"] = 20
    with pytest.raises(HTTPException, match="120 generated turns"):
        simulator.PerspectiveSimulatorService().simulate(PerspectiveSimulateRequest(**payload))


def test_graph_cardinality_text_and_ids_are_bounded(payload):
    import copy
    import pytest
    from pydantic import ValidationError
    for field, count in [("nodes", 65), ("edges", 129)]:
        oversized = copy.deepcopy(payload)
        oversized[field] = [oversized[field][0]] * count
        with pytest.raises(ValidationError): PerspectiveSimulateRequest(**oversized)
    oversized = copy.deepcopy(payload)
    oversized["nodes"][0]["data"]["description"] = "x" * 8001
    with pytest.raises(ValidationError): PerspectiveSimulateRequest(**oversized)
    duplicate = copy.deepcopy(payload)
    duplicate["nodes"].append(duplicate["nodes"][0])
    with pytest.raises(ValidationError): PerspectiveSimulateRequest(**duplicate)
