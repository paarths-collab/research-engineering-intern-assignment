"""Pure helpers for building the aggregated /health payload.

Kept free of heavy imports so it can be tested without loading main.py.
"""

# Order matches the sub-apps mounted in main.py.
EXPECTED_MODULES = [
    "polarize_1",
    "networkgraph",
    "streamgraph2",
    "globe",
    "globe_pipeline",
    "hybrid_chatbot",
    "perspective",
]

# Sub-components whose load failure degrades a parent module. The child keeps
# its own key in module_load_errors; the parent is reported as "degraded" when
# it is still mounted, or "unavailable" if it failed as well.
COMPONENT_PARENTS = {
    "globe_pipeline": "globe",
}


def _module_status(name: str, module_errors: dict[str, str]) -> str:
    if name in module_errors:
        return "unavailable"
    for child, parent in COMPONENT_PARENTS.items():
        if parent == name and child in module_errors:
            return "degraded"
    return "mounted"


def build_health_payload(module_names: list[str], module_errors: dict[str, str]) -> dict:
    """Summarise which sub-apps are mounted and which failed to load.

    Status is "degraded" when any error is recorded, but callers should still
    return HTTP 200 so platform health checks keep passing.
    """
    modules = {name: _module_status(name, module_errors) for name in module_names}
    return {
        "status": "ok" if not module_errors else "degraded",
        "modules": modules,
        "module_load_errors": dict(module_errors),
    }
