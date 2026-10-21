"""Tests for the aggregated health payload. Imports only service_health (not main)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from service_health import EXPECTED_MODULES, build_health_payload  # noqa: E402

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


def test_globe_pipeline_failure_degrades_globe_in_real_order():
    payload = build_health_payload(EXPECTED_MODULES, {"globe_pipeline": "no pipeline"})

    assert payload["status"] == "degraded"
    assert payload["modules"]["globe"] == "degraded"
    assert payload["modules"]["globe_pipeline"] == "unavailable"
    assert payload["modules"]["hybrid_chatbot"] == "mounted"
    assert payload["modules"]["perspective"] == "mounted"
    assert payload["module_load_errors"] == {"globe_pipeline": "no pipeline"}
    assert list(payload["modules"]) == EXPECTED_MODULES


def test_globe_and_pipeline_both_failed_marks_globe_unavailable():
    errors = {"globe": "boom", "globe_pipeline": "no pipeline"}
    payload = build_health_payload(EXPECTED_MODULES, errors)

    assert payload["modules"]["globe"] == "unavailable"
    assert payload["modules"]["globe_pipeline"] == "unavailable"
    assert payload["module_load_errors"] == errors


def test_all_expected_modules_ok_in_real_order():
    payload = build_health_payload(EXPECTED_MODULES, {})

    assert payload["status"] == "ok"
    assert set(payload["modules"].values()) == {"mounted"}
