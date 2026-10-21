"""Tests for the aggregated health payload. Imports only service_health (not main)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from service_health import build_health_payload  # noqa: E402

NAMES = ["polarize_1", "networkgraph", "streamgraph2", "globe", "hybrid_chatbot", "perspective"]


def test_all_ok_reports_ok_and_all_mounted():
    payload = build_health_payload(NAMES, {})

    assert payload["status"] == "ok"
    assert payload["modules"] == {name: "mounted" for name in NAMES}
    assert payload["module_load_errors"] == {}


def test_one_error_reports_degraded_and_preserves_error():
    payload = build_health_payload(NAMES, {"globe": "boom"})

    assert payload["status"] == "degraded"
    assert payload["modules"]["globe"] == "unavailable"
    assert all(payload["modules"][n] == "mounted" for n in NAMES if n != "globe")
    assert payload["module_load_errors"] == {"globe": "boom"}
