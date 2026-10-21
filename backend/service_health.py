"""Pure helpers for building the aggregated /health payload.

Kept free of heavy imports so it can be tested without loading main.py.
"""


def build_health_payload(module_names: list[str], module_errors: dict[str, str]) -> dict:
    """Summarise which sub-apps are mounted and which failed to load.

    Status is "degraded" when any error is recorded, but callers should still
    return HTTP 200 so platform health checks keep passing.
    """
    modules = {
        name: "unavailable" if name in module_errors else "mounted"
        for name in module_names
    }
    return {
        "status": "ok" if not module_errors else "degraded",
        "modules": modules,
        "module_load_errors": dict(module_errors),
    }
