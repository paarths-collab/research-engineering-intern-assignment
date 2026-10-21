import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from perspective.services import simulator_service  # noqa: E402


class _FakeResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def make_fake_client(content=None, error=None):
    """Build a stand-in for httpx.Client; never touches the network."""

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *args, **kwargs):
            if error is not None:
                raise error
            return _FakeResponse(content)

        def get(self, *args, **kwargs):
            raise AssertionError("unexpected HTTP GET in test")

    return _FakeClient


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("PERSPECTIVE_GROQ_MODEL", raising=False)
    monkeypatch.setattr(
        simulator_service.PerspectiveSimulatorService,
        "_fetch_globe_events",
        lambda self, limit=20: [],
    )
    # Any un-stubbed outbound HTTP fails loudly instead of reaching the network.
    monkeypatch.setattr(simulator_service.httpx, "Client", make_fake_client(error=AssertionError("unstubbed HTTP call")))


@pytest.fixture
def payload():
    def node(nid, ntype, label, **extra):
        return {"id": nid, "type": ntype, "position": {"x": 0, "y": 0}, "data": {"label": label, **extra}}

    return {
        "nodes": [
            node("p1", "persona", "Alice", description="cautious"),
            node("p2", "persona", "Bob", description="bold"),
            node("n1", "news", "Port strike widens", description="Dockworkers extend walkout."),
            node("d1", "debate", "Debate"),
        ],
        "edges": [
            {"id": "e1", "source": "p1", "target": "d1"},
            {"id": "e2", "source": "p2", "target": "d1"},
            {"id": "e3", "source": "d1", "target": "n1"},
        ],
        "debate_rounds": 2,
    }
