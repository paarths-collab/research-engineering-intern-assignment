"""Real auth-library/database integration, isolated to a temporary local store."""
import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

import user_auth as auth

PASSWORD = "example-user-password-42"
EMAIL = "reader@example.com"


@pytest.fixture(autouse=True)
def local_auth_database(monkeypatch, tmp_path):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AUTH_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'accounts.sqlite'}")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("USER_DAILY_ANALYSIS_LIMIT", "3")


def run_scenario(scenario):
    async def run():
        assert await auth.initialize_auth()
        app = FastAPI()
        app.include_router(auth.router)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                await scenario(client)
        finally:
            await auth.close_auth()
    asyncio.run(run())


async def signup(client, **extra):
    return await client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD, **extra})


async def login(client, **extra):
    return await client.post("/api/auth/login", data={"username": EMAIL, "password": PASSWORD, **extra})


def scope_for(token):
    return {"headers": [(b"cookie", f"{auth.COOKIE_NAME}={token}".encode())]}


def test_signup_login_cookie_me_logout_and_hashed_storage():
    async def scenario(client):
        assert (await client.get("/api/auth/me")).status_code == 401
        response = await signup(client, email="  READER@EXAMPLE.COM ")
        assert response.status_code == 201, response.text
        created = response.json()
        assert set(created) == {"id", "email"}
        assert created["email"] == EMAIL
        assert (await signup(client)).status_code == 400
        async with auth._sessions() as session:
            user = (await session.execute(select(auth.User))).scalar_one()
            assert user.hashed_password.startswith("$argon2id$")
            assert not user.is_superuser and not user.is_verified and user.is_active
            assert PASSWORD not in user.hashed_password
        response = await login(client, username="  READER@EXAMPLE.COM ")
        assert response.status_code == 204
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie
        assert "path=/" in cookie and "max-age=86400" in cookie and "domain=" not in cookie
        assert "secure" not in cookie  # explicit local override only
        token = client.cookies[auth.COOKIE_NAME]
        assert len(token) == 43
        async with auth._sessions() as session:
            stored = (await session.execute(select(auth.AccessToken))).scalar_one()
            assert stored.token != token
            assert stored.token == hashlib.sha256(token.encode()).hexdigest()
        assert (await client.get("/api/auth/me")).json() == created
        assert await auth.resolve_session(scope_for(token)) == created
        response = await client.post("/api/auth/logout")
        assert response.status_code == 204
        assert "max-age=0" in response.headers["set-cookie"].lower()
        assert (await client.get("/api/auth/me")).status_code == 401
        assert await auth.resolve_session(scope_for(token)) is None
    run_scenario(scenario)


@pytest.mark.parametrize("field", ["is_superuser", "is_active", "is_verified", "role", "admin"])
def test_signup_rejects_privilege_or_unknown_fields(field):
    async def scenario(client):
        assert (await signup(client, **{field: True})).status_code == 422
        async with auth._sessions() as session:
            assert not (await session.execute(select(auth.User))).scalars().all()
    run_scenario(scenario)


def test_public_registration_schema_has_no_privilege_fields():
    assert set(auth.UserCreate.model_json_schema()["properties"]) == {"email", "password"}


@pytest.mark.parametrize("password", ["short", "x" * 129, "😀" * 129, "😀" * 3])
def test_password_character_bounds(password):
    async def scenario(client):
        assert (await signup(client, password=password)).status_code == 422
    run_scenario(scenario)


@pytest.mark.parametrize("password", ["😀" * 12, "😀" * 33])
def test_unicode_password_signup_hash_and_login(password):
    async def scenario(client):
        assert (await signup(client, password=password)).status_code == 201
        async with auth._sessions() as session:
            user = (await session.execute(select(auth.User))).scalar_one()
            assert user.hashed_password.startswith("$argon2id$")
            assert password not in user.hashed_password
        assert (await login(client, password=password)).status_code == 204
        assert (await client.get("/api/auth/me")).json()["email"] == EMAIL
    run_scenario(scenario)


def test_password_invalid_unicode_rejected_before_hashing():
    assert not auth._valid_password("\ud800" * 12)


def test_bad_credentials_tampered_expired_and_inactive_sessions():
    async def scenario(client):
        created = (await signup(client)).json()
        assert (await login(client, password="different-valid-password")).status_code == 400
        assert (await login(client, username="absent@example.com")).status_code == 400
        assert (await login(client)).status_code == 204
        token = client.cookies[auth.COOKIE_NAME]
        assert await auth.resolve_session(scope_for("x" * 43)) is None
        assert await auth.resolve_session(scope_for(token + "x")) is None
        async with auth._sessions() as session:
            await session.execute(update(auth.User).where(auth.User.id == uuid.UUID(created["id"])).values(is_active=False))
            await session.commit()
        assert (await client.get("/api/auth/me")).status_code == 401
        assert (await login(client)).status_code == 400
        async with auth._sessions() as session:
            await session.execute(update(auth.User).values(is_active=True, is_superuser=True))
            await session.execute(update(auth.AccessToken).values(created_at=datetime.now(timezone.utc) - timedelta(days=2)))
            await session.commit()
        assert await auth.resolve_session(scope_for(token)) is None
        assert (await login(client)).status_code == 204
        # Even externally changed flags never appear in the public session result.
        assert (await client.get("/api/auth/me")).json() == created
    run_scenario(scenario)


def test_daily_quota_atomic_concurrency_restart_and_utc_day():
    async def scenario(client):
        user_id = (await signup(client)).json()["id"]
        outcomes = await asyncio.gather(*(auth.reserve_analysis(user_id) for _ in range(12)))
        assert outcomes.count(True) == 3
        assert outcomes.count(False) == 9
        await auth.close_auth()
        assert await auth.initialize_auth()
        assert not await auth.reserve_analysis(user_id)
        async with auth._sessions() as session:
            usage = (await session.execute(select(auth.DailyAnalysisUsage))).scalar_one()
            assert usage.used == 3 and usage.day == datetime.now(timezone.utc).date()
            usage.day -= timedelta(days=1)
            await session.commit()
        assert await auth.reserve_analysis(user_id)
    run_scenario(scenario)


def test_session_survives_process_store_restart():
    async def scenario(client):
        created = (await signup(client)).json()
        assert (await login(client)).status_code == 204
        await auth.close_auth()
        assert await auth.initialize_auth()
        assert (await client.get("/api/auth/me")).json() == created
    run_scenario(scenario)


def test_missing_database_fails_closed_without_exposing_configuration(monkeypatch):
    async def run():
        await auth.close_auth()
        monkeypatch.delenv("AUTH_DATABASE_URL")
        assert not await auth.initialize_auth()
        app = FastAPI()
        app.include_router(auth.router)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            assert (await client.get("/api/auth/status")).json() == {"configured": False}
            assert (await signup(client)).status_code == 503
            assert (await login(client)).status_code == 503
            assert (await client.get("/api/auth/me")).status_code == 503
        with pytest.raises(auth.AuthUnavailableError, match="temporarily unavailable"):
            await auth.resolve_session(scope_for("x" * 43))
        with pytest.raises(auth.AuthUnavailableError):
            await auth.reserve_analysis(str(uuid.uuid4()))
    asyncio.run(run())


def test_production_disallows_sqlite_and_forces_secure_cookies(monkeypatch):
    async def run():
        monkeypatch.setenv("RENDER", "true")
        assert auth._cookie_secure()
        assert not await auth.initialize_auth()
        assert not auth.auth_configured()
        await auth.close_auth()
    asyncio.run(run())


def test_invalid_configuration_is_sanitized(monkeypatch):
    async def run():
        monkeypatch.setenv("AUTH_DATABASE_URL", "invalid-secret://private-user:private-password@example.invalid/database")
        assert not await auth.initialize_auth()
        assert auth.auth_configuration_error == auth.UNAVAILABLE_DETAIL
        assert "private" not in auth.auth_configuration_error
        await auth.close_auth()
    asyncio.run(run())
