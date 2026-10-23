"""Admission tests use ASGI and fake providers; no external requests or secrets."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

import api_security as security

TOKEN = "example-test-operator-token-" + "x" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("NARRATIVE_API_TOKEN", TOKEN)
    monkeypatch.setenv("RATE_LIMIT_MAX", "1000")
    monkeypatch.setenv("WORK_LIMIT_MAX", "1000")


def make_app(**limits):
    app = FastAPI()
    app.add_middleware(security.APISecurityMiddleware, **limits)
    child = FastAPI()
    child.add_middleware(security.APISecurityMiddleware, standalone=True)

    @child.api_route("/action", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
    def action():
        return {"ok": True}

    for module in ["polar", "network", "stream", "globe", "chatbot", "perspective"]:
        app.mount(f"/api/{module}", child)
    app.mount("/api", child)
    app.add_api_route("/diag", lambda: {"private": True})
    app.add_api_route("/health", lambda: {"ok": True})
    return app


@pytest.mark.parametrize("module", ["polar", "network", "stream", "globe", "chatbot", "perspective", ""])
def test_every_mount_and_polar_alias_require_auth(module):
    client = TestClient(make_app())
    path = f"/api/{module}/action" if module else "/api/action"
    assert client.post(path).status_code == 401
    assert client.post(path, headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.post(path, headers=AUTH).json() == {"ok": True}
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_all_write_methods_are_protected(method):
    assert getattr(TestClient(make_app()), method)("/api/action").status_code == 401


@pytest.mark.parametrize("token", ["", "too-short", " " + TOKEN])
def test_missing_or_weak_configuration_fails_closed(monkeypatch, token):
    monkeypatch.setenv("NARRATIVE_API_TOKEN", token)
    client = TestClient(make_app())
    assert client.post("/api/action", headers=AUTH).status_code == 503
    assert client.get("/api/action").status_code == 200
    assert client.get("/health").status_code == 200


def test_diagnostics_require_auth_and_query_token_is_not_accepted():
    client = TestClient(make_app())
    assert client.get("/diag").status_code == 401
    assert client.get("/diag", headers=AUTH).status_code == 200
    assert client.post("/api/action", params={"token": TOKEN}).status_code == 401


def test_polar_aliases_share_a_rate_bucket_and_mount_is_not_double_counted():
    client = TestClient(make_app(read_limit=2))
    assert client.post("/api/polar/action", headers=AUTH).status_code == 200
    assert client.post("/api/action", headers=AUTH).status_code == 200
    response = client.post("/api/polar/action", headers=AUTH)
    assert response.status_code == 429 and response.headers["retry-after"]
    assert client.get("/api/network/action").status_code == 200


def test_work_quota_is_global_across_modules_and_client_addresses():
    async def run():
        app = make_app(work_limit=1)
        for ip, module, expected in [("192.0.2.1", "network", 200), ("192.0.2.2", "stream", 429)]:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app, client=(ip, 1)), base_url="http://test") as client:
                assert (await client.post(f"/api/{module}/action", headers=AUTH)).status_code == expected
    asyncio.run(run())


@pytest.mark.parametrize("payload", [{"text": "x" * 8001}, {"items": [0] * 513}, {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": 1}}}}}}}}}}}}}])
def test_oversized_text_collections_and_nesting_rejected(payload):
    assert TestClient(make_app()).post("/api/action", headers=AUTH, json=payload).status_code == 422


def test_malformed_and_chunked_oversized_bodies_rejected_before_handler():
    client = TestClient(make_app())
    assert client.post("/api/action", headers=AUTH, content=b'{').status_code == 422

    async def run():
        reached = False
        async def handler(scope, receive, send):
            nonlocal reached
            reached = True
        middleware = security.APISecurityMiddleware(handler)
        messages = iter([{"type": "http.request", "body": b"x" * 140000, "more_body": True},
                         {"type": "http.request", "body": b"x" * 140000, "more_body": False}])
        output = []
        async def receive(): return next(messages)
        async def send(message): output.append(message)
        await middleware({"type": "http", "method": "POST", "path": "/api/action", "client": ("test", 1),
                          "headers": [(b"authorization", f"Bearer {TOKEN}".encode()), (b"content-length", b"1")]}, receive, send)
        assert output[0]["status"] == 413 and not reached
    asyncio.run(run())


def test_concurrency_slot_includes_background_task_and_releases_on_completion():
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        app = FastAPI()
        app.add_middleware(security.APISecurityMiddleware, concurrency=1)
        async def background():
            started.set()
            await release.wait()
        @app.post("/api/job")
        async def job(tasks: BackgroundTasks):
            tasks.add_task(background)
            return {"accepted": True}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test", headers=AUTH) as client:
            first = asyncio.create_task(client.post("/api/job"))
            await started.wait()
            try:
                assert (await client.post("/api/job")).status_code == 429
            finally:
                release.set()
            assert (await first).status_code == 200
            assert (await client.post("/api/job")).status_code == 200
    asyncio.run(run())


def test_provider_budget_shared_across_threads_and_swallowed_fallbacks(monkeypatch):
    original = security.WorkBudget
    monkeypatch.setattr(security, "WorkBudget", lambda: original(remaining=2))
    app = FastAPI()
    app.add_middleware(security.APISecurityMiddleware)
    attempts = []
    @app.post("/api/work")
    async def work():
        async def call():
            try:
                await asyncio.to_thread(security.consume_provider_call)
                attempts.append("fake outbound")
            except security.WorkLimitExceeded:
                pass  # Even a service that swallows this must not report success.
        await asyncio.gather(*(call() for _ in range(10)))
        return {"fallback": True}
    assert TestClient(app).post("/api/work", headers=AUTH).status_code == 429
    assert len(attempts) == 2
    assert security._work_budget.get() is None


def test_budget_deadline_and_atomic_reservation():
    budget = security.WorkBudget(remaining=7)
    def call(_):
        try: budget.consume(); return 1
        except security.WorkLimitExceeded: return 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(call, range(100))) == 7
    with pytest.raises(security.WorkLimitExceeded):
        security.WorkBudget(deadline=0).consume()


def test_rate_state_expires_and_is_bounded(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(security, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    app = make_app(read_limit=1, work_limit=1, window=5)
    client = TestClient(app)
    assert client.post("/api/action", headers=AUTH).status_code == 200
    assert client.post("/api/action", headers=AUTH).status_code == 429
    clock[0] += 6
    assert client.post("/api/action", headers=AUTH).status_code == 200
    limiter = app.middleware_stack.app
    for n in range(5000): limiter.read_buckets[(str(n), "polar")] = [clock[0]]
    assert client.get("/api/network/action").status_code == 200
    assert len(limiter.read_buckets) == 4096


def test_standalone_chatbot_denies_before_pipeline(monkeypatch):
    from hybrid_chatbot import api
    monkeypatch.setattr(api.app, "middleware_stack", None)
    def forbidden(*args, **kwargs): raise AssertionError("pipeline must not be invoked")
    monkeypatch.setattr(api.pipeline, "run", forbidden)
    client = TestClient(api.app)
    assert client.post("/query", json={"query": "test"}).status_code == 401
    assert client.post("/query", headers=AUTH, json={"query": "x" * 8001}).status_code == 422


@pytest.mark.parametrize("mounted", [False, True])
def test_uncaught_work_limit_returns_429_and_releases_slot(monkeypatch, mounted):
    original = security.WorkBudget
    monkeypatch.setattr(security, "WorkBudget", lambda: original(remaining=1))
    app, child = FastAPI(), FastAPI()
    app.add_middleware(security.APISecurityMiddleware, concurrency=1)
    target = child if mounted else app
    @target.post("/work" if mounted else "/api/work")
    async def work():
        security.consume_provider_call()
        security.consume_provider_call()
    if mounted: app.mount("/api", child)
    client = TestClient(app)
    for _ in range(3):
        response = client.post("/api/work", headers=AUTH)
        assert response.status_code == 429
        assert "provider-call" in response.json()["detail"]
        assert response.headers["retry-after"]
    assert app.middleware_stack.app.active == 0


def test_nonfinite_numbers_rejected():
    assert TestClient(make_app()).post("/api/action", headers=AUTH, content='{"value": NaN}').status_code == 422


def test_real_chatbot_client_cannot_send_after_budget_exhaustion(monkeypatch):
    from hybrid_chatbot import llm_client
    monkeypatch.setattr(llm_client, "LLM_API_KEY", "fake-provider-key")
    sent = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs):
            sent.append("outbound")
            return httpx.Response(200, json={"choices": [{"message": {"content": "fake reply"}}]})
    monkeypatch.setattr(llm_client.httpx, "Client", Client)
    budget_token = security._work_budget.set(security.WorkBudget(remaining=1))
    try:
        client = llm_client.LLMClient()
        assert client.generate("system", "user")[0] == "fake reply"
        with pytest.raises(security.WorkLimitExceeded): client.generate("system", "user")
        assert len(sent) == 1
    finally:
        security._work_budget.reset(budget_token)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_http_redirect_hops_share_attempt_budget(asynchronous):
    calls = []
    def redirect(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": f"https://example.test/hop{len(calls)}"})
    budget = security.WorkBudget(remaining=2)
    budget_token = security._work_budget.set(budget)
    try:
        if asynchronous:
            async def run():
                async with httpx.AsyncClient(transport=httpx.MockTransport(redirect), follow_redirects=True,
                    event_hooks={"request": [security.count_async_httpx_redirect]}) as client:
                    security.consume_provider_call()
                    await client.get("https://example.test/start")
            with pytest.raises(security.WorkLimitExceeded): asyncio.run(run())
        else:
            with httpx.Client(transport=httpx.MockTransport(redirect), follow_redirects=True,
                event_hooks={"request": [security.count_httpx_redirect]}) as client:
                security.consume_provider_call()
                with pytest.raises(security.WorkLimitExceeded): client.get("https://example.test/start")
        assert len(calls) == 2
        assert budget.exhausted
    finally:
        security._work_budget.reset(budget_token)
