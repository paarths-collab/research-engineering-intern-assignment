"""Exercise member/admin boundaries without provider calls or production secrets."""
import pytest
import asyncio
import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from fastapi.security import OAuth2PasswordRequestForm

from api_security import APISecurityMiddleware, api_validation_error, user_analysis_allowed

OPERATOR = "public-fixture-operator-" + "x" * 32
CSRF = {"X-Narrative-CSRF": "1", "Origin": "https://narrative.example"}


def build(monkeypatch, principal=None, reserve=None, **limits):
    monkeypatch.setenv("NARRATIVE_API_TOKEN", OPERATOR)
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://narrative.example")
    app = FastAPI()
    async def resolve(scope):
        return principal if dict(scope.get("headers", [])).get(b"cookie") == b"session=valid" else None
    async def reserve_default(user_id):
        return True
    app.add_middleware(APISecurityMiddleware, user_authenticator=resolve,
                       analysis_reserver=reserve or reserve_default, read_limit=1000, work_limit=1000, **limits)
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    def handler(path):
        return {"ok": True}
    app.add_api_route("/diag", lambda: {"private": True})
    return TestClient(app)


@pytest.mark.parametrize("path", [
    "/api/chatbot/query", "/api/perspective/simulate", "/api/polar/ai-analysis", "/api/ai-analysis",
    "/api/intelligence-brief", "/api/polar/intelligence-brief", "/api/network/intelligence/analyze",
    "/api/network/intelligence/narrative/story-1/analyze", "/api/stream/api/media-brief",
    "/api/stream/api/analyze-event", "/api/stream/api/extract-topics", "/api/stream/api/topic-analysis",
    "/api/globe/events/news", "/api/globe/events/headline-analysis", "/api/globe/events/ai-analysis",
    "/api/globe/events/event-1/analyze", "/api/globe/events/event-1/news-analysis", "/api/globe/events/event-1/ai-analysis",
])
def test_members_can_only_run_explicit_analysis_posts(monkeypatch, path):
    client = build(monkeypatch, {"id": "member-1"})
    assert client.post(path, json={}).status_code == 401
    response = client.post(path, json={}, headers={**CSRF, "Cookie": "session=valid"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert client.put(path, json={}, headers={**CSRF, "Cookie": "session=valid"}).status_code == 403


@pytest.mark.parametrize("path", ["/diag", "/api/globe/pipeline/run", "/api/globe/pipeline/run/sync",
                                      "/api/stream/api/spike-analysis/job-1", "/api/future/admin-action"])
def test_even_privileged_client_claims_do_not_grant_admin(monkeypatch, path):
    client = build(monkeypatch, {"id": "member-1", "is_superuser": True, "role": "admin"})
    method = client.get if path == "/diag" else client.post
    assert method(path, headers={**CSRF, "Cookie": "session=valid"}).status_code == 403
    assert method(path, headers={"Authorization": f"Bearer {OPERATOR}"}).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"Origin": "https://narrative.example"},
                                      {"X-Narrative-CSRF": "1", "Origin": "https://evil.example"},
                                      {"X-Narrative-CSRF": "1", "Origin": "null"}])
def test_cookie_writes_require_csrf_and_trusted_origin(monkeypatch, headers):
    client = build(monkeypatch, {"id": "member-1"})
    for path in ["/api/chatbot/query", "/api/auth/login", "/api/auth/register", "/api/auth/logout"]:
        assert client.post(path, json={}, headers={**headers, "Cookie": "session=valid"}).status_code == 403


def test_auth_form_is_bounded_and_separate_from_analysis_admission(monkeypatch):
    client = build(monkeypatch)
    assert client.post("/api/auth/login", data={"username": "member@example.invalid", "password": "fixture-password"}, headers=CSRF).status_code == 200
    assert client.post("/api/auth/login", content=b"x" * 16385, headers=CSRF).status_code == 413
    assert client.get("/api/auth/me").headers["cache-control"] == "no-store"


def test_auth_attempts_are_limited_before_the_handler(monkeypatch):
    client = build(monkeypatch)
    for _ in range(10):
        assert client.post("/api/auth/register", json={"email": "member@example.invalid"}, headers=CSRF).status_code == 200
    assert client.post("/api/auth/register", json={"email": "member@example.invalid"}, headers=CSRF).status_code == 429
    assert client.get("/api/chatbot/health").status_code == 200


def test_form_account_limit_matches_the_actual_login_account_across_clients(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://narrative.example")
    app = FastAPI()
    app.add_middleware(APISecurityMiddleware, read_limit=1000)
    accounts = []
    @app.post("/api/auth/login")
    def login(credentials: OAuth2PasswordRequestForm = Depends()):
        accounts.append(credentials.username)
        return {"ok": True}
    async def run():
        headers = {**CSRF, "Content-Type": "application/x-www-form-urlencoded"}
        for number in range(11):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app, client=(f"192.0.2.{number}", 1)), base_url="http://test") as client:
                duplicate = f"username=decoy{number}&username=member%40example.com&password=fixture-password"
                assert (await client.post("/api/auth/login", content=duplicate, headers=headers)).status_code == 422
                expected = 200 if number < 10 else 429
                assert (await client.post("/api/auth/login", data={"username": "member@example.com", "password": "fixture-password"}, headers=CSRF)).status_code == expected
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            assert (await client.post("/api/auth/login", files={"username": (None, "member@example.com"), "password": (None, "fixture-password")}, headers=CSRF)).status_code == 415
    asyncio.run(run())
    assert accounts == ["member@example.com"] * 10


def test_surrogate_email_fails_without_echoing_credentials(monkeypatch):
    client = build(monkeypatch)
    response = client.post("/api/auth/register", content=b'{"email":"\\ud800", "password":"sensitive-fixture-password"}', headers={**CSRF, "Content-Type": "application/json"})
    assert response.status_code == 422
    assert "sensitive-fixture-password" not in response.text


def test_members_have_per_account_and_durable_quota_checks(monkeypatch):
    reservations = []
    async def reserve(uid):
        reservations.append(uid)
        return len(reservations) <= 2
    client = build(monkeypatch, {"id": "member-1"}, reserve)
    for expected in [200, 200, 429, 429]:
        response = client.post("/api/chatbot/query", json={}, headers={**CSRF, "Cookie": "session=valid"})
        assert response.status_code == expected
    assert reservations == ["member-1"] * 3
    assert client.app.middleware_stack.app.active == 0


def test_member_auth_is_independent_of_operator_configuration(monkeypatch):
    client = build(monkeypatch, {"id": "member-1"})
    monkeypatch.delenv("NARRATIVE_API_TOKEN")
    assert client.post("/api/chatbot/query", json={}, headers={**CSRF, "Cookie": "session=valid"}).status_code == 200
    assert client.get("/diag", headers={"Cookie": "session=valid"}).status_code == 403


def test_database_auth_errors_fail_closed(monkeypatch):
    app = FastAPI()
    async def broken(scope):
        raise RuntimeError("private-database-details")
    app.add_middleware(APISecurityMiddleware, user_authenticator=broken)
    client = TestClient(app)
    response = client.post("/api/chatbot/query", headers=CSRF, json={})
    assert response.status_code == 503
    assert "private-database-details" not in response.text


def test_allowlist_is_exact_and_defaults_deny():
    for path in ["/api/chatbot/query/", "/api/chatbot/query/extra", "/api/network/intelligence/narrative/a/b/analyze",
                 "/api/globe/events/a/b/analyze", "/api/globe/pipeline/run", "/api/unknown"]:
        assert not user_analysis_allowed(path, "POST")


def test_real_cookie_signup_analysis_admin_separation_logout_and_redaction(monkeypatch, tmp_path):
    import user_auth as auth
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("AUTH_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'accounts.sqlite'}")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://narrative.example")
    monkeypatch.setenv("NARRATIVE_API_TOKEN", OPERATOR)
    app = FastAPI()
    app.include_router(auth.router)
    app.add_exception_handler(RequestValidationError, api_validation_error)
    app.add_middleware(APISecurityMiddleware, user_authenticator=auth.resolve_session, analysis_reserver=auth.reserve_analysis)
    executed = []
    @app.post("/api/chatbot/query")
    def analysis(request: Request):
        executed.append("analysis")
        return {"user_id": request.scope["narrative_user_id"]}
    @app.post("/api/globe/pipeline/run")
    def collection():
        executed.append("collection")
        return {"ok": True}
    async def run():
        assert await auth.initialize_auth()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                credentials = {"email": "reader@example.com", "password": "example-user-password-42"}
                assert (await client.post("/api/auth/register", json=credentials)).status_code == 403
                registered = await client.post("/api/auth/register", json=credentials, headers=CSRF)
                assert registered.status_code == 201, registered.text
                assert registered.headers["cache-control"] == "no-store"
                assert credentials["password"] not in registered.text
                malformed = await client.post("/api/auth/register", content=b'{"email":"other@example.com","password":"\\ud800"}', headers={**CSRF, "Content-Type": "application/json"})
                assert malformed.status_code == 422
                assert all(set(e) <= {"loc", "msg", "type"} for e in malformed.json()["detail"])
                logged_in = await client.post("/api/auth/login", data={"username": credentials["email"], "password": credentials["password"]}, headers=CSRF)
                assert logged_in.status_code == 204, logged_in.text
                token = client.cookies[auth.COOKIE_NAME]
                assert "httponly" in logged_in.headers["set-cookie"].lower()
                assert logged_in.headers["cache-control"] == "no-store"
                assert (await client.get("/api/auth/me")).json() == registered.json()
                assert (await client.post("/api/chatbot/query", json={})).status_code == 403
                assert (await client.post("/api/chatbot/query", json={}, headers={**CSRF, "Origin": "https://evil.example"})).status_code == 403
                result = await client.post("/api/chatbot/query", json={}, headers=CSRF)
                assert result.status_code == 200 and result.json()["user_id"] == registered.json()["id"]
                assert (await client.post("/api/globe/pipeline/run", json={}, headers=CSRF)).status_code == 403
                assert (await client.post("/api/globe/pipeline/run", json={}, headers={"Authorization": f"Bearer {OPERATOR}"})).status_code == 200
                assert (await client.post("/api/auth/logout", headers=CSRF)).status_code == 204
                replay = await client.post("/api/chatbot/query", json={}, headers={**CSRF, "Cookie": f"{auth.COOKIE_NAME}={token}"})
                assert replay.status_code == 401
                assert executed == ["analysis", "collection"]
        finally:
            await auth.close_auth()
    asyncio.run(run())
