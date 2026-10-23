"""User accounts and revocable opaque sessions, isolated from analytics data.

Production uses PostgreSQL in the private ``narrative_auth`` schema. SQLite is
available only through an explicit AUTH_DATABASE_URL for local development/tests.
No user account, including an account with database flags changed externally,
grants access to operator-only endpoints.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from http.cookies import CookieError, SimpleCookie
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, exceptions, schemas
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import (
    SQLAlchemyAccessTokenDatabase,
    SQLAlchemyBaseAccessTokenTableUUID,
)
from fastapi_users_db_sqlalchemy.generics import GUID
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator
from sqlalchemy import Date, ForeignKey, Integer, MetaData, String, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import CreateSchema

AUTH_SCHEMA = "narrative_auth"
COOKIE_NAME = "narrative_session"
SESSION_LIFETIME_SECONDS = 24 * 60 * 60
UNAVAILABLE_DETAIL = "User authentication is temporarily unavailable"


class AuthUnavailableError(RuntimeError):
    """An unavailable auth store must never fall through as authenticated."""


class Base(DeclarativeBase):
    metadata = MetaData(schema=AUTH_SCHEMA)


class User(SQLAlchemyBaseUserTableUUID, Base):
    pass


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    # Persist a digest of each randomly generated opaque cookie, never its value.
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey(f"{AUTH_SCHEMA}.user.id", ondelete="CASCADE"), nullable=False
    )


class DailyAnalysisUsage(Base):
    __tablename__ = "daily_analysis_usage"
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey(f"{AUTH_SCHEMA}.user.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    used: Mapped[int] = mapped_column(Integer, nullable=False)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr


def _valid_password(password: str) -> bool:
    if not isinstance(password, str):
        return False
    try:
        password.encode("utf-8")
        return 12 <= len(password) <= 128
    except UnicodeError:
        return False


class UserCreate(schemas.CreateUpdateDictModel):
    # FastAPI Users' safe-create methods with only public registration fields.
    # Its full BaseUserCreate also exposes privilege flags in generated OpenAPI.
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str

    @model_validator(mode="before")
    @classmethod
    def reject_privilege_fields(cls, value):
        if isinstance(value, dict) and {"is_active", "is_superuser", "is_verified"}.intersection(value):
            raise ValueError("Account privilege fields cannot be supplied")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def password_length(cls, value):
        if not _valid_password(value):
            raise ValueError("Password must contain between 12 and 128 characters")
        return value


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    async def validate_password(self, password: str, user):
        if not _valid_password(password):
            raise exceptions.InvalidPasswordException(
                reason="Password must contain between 12 and 128 characters"
            )

    async def create(self, user_create, safe=False, request=None):
        # Always enforce safe creation, even if a future caller forgets the flag.
        try:
            return await super().create(user_create, safe=True, request=request)
        except IntegrityError:
            await self.user_db.session.rollback()
            raise exceptions.UserAlreadyExists() from None

    async def authenticate(self, credentials: OAuth2PasswordRequestForm):
        if not _valid_password(credentials.password):
            return None
        credentials.username = credentials.username.strip().lower()
        return await super().authenticate(credentials)


class HashedDatabaseStrategy(DatabaseStrategy):
    """Keep FastAPI Users' expiry/revocation semantics with hashed DB tokens."""

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def write_token(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        await self.database.create({"token": self._digest(token), "user_id": user.id})
        # Expired sessions have no further use; the timestamp column is indexed.
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=SESSION_LIFETIME_SECONDS)
        await self.database.session.execute(delete(AccessToken).where(AccessToken.created_at < cutoff))
        await self.database.session.commit()
        return token

    async def read_token(self, token, user_manager):
        if token is None or len(token) != 43:
            return None
        return await super().read_token(self._digest(token), user_manager)

    async def destroy_token(self, token, user):
        return await super().destroy_token(self._digest(token), user)


_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None
_dialect: str | None = None
_daily_limit = 20
auth_configuration_error: str | None = UNAVAILABLE_DETAIL


def auth_configured() -> bool:
    return _sessions is not None and auth_configuration_error is None


def _cookie_secure() -> bool:
    # Render always requires secure cookies, regardless of a local override.
    return bool(os.getenv("RENDER")) or os.getenv("AUTH_COOKIE_SECURE", "true").lower() != "false"


async def initialize_auth() -> bool:
    """Initialize only auth tables; missing/failed configuration is fail-closed.

    Call from the application lifespan. A broken user store must not prevent
    public dashboards or the separately authenticated operator interface starting.
    Configuration errors are deliberately generic: DB URLs can contain secrets.
    """
    global _engine, _sessions, _dialect, _daily_limit, auth_configuration_error
    await close_auth()
    auth_configuration_error = UNAVAILABLE_DETAIL
    raw_url = os.getenv("AUTH_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not raw_url:
        return False
    engine = None
    try:
        limit = int(os.getenv("USER_DAILY_ANALYSIS_LIMIT", "20"))
        if not 1 <= limit <= 1000:
            return False
        url = make_url(raw_url)
        options = {"hide_parameters": True, "pool_pre_ping": True}
        if url.drivername in {"postgres", "postgresql", "postgresql+asyncpg"}:
            url = url.set(drivername="postgresql+asyncpg")
            # asyncpg calls libpq's sslmode option "ssl".
            if "sslmode" in url.query:
                query = dict(url.query)
                query["ssl"] = query.pop("sslmode")
                url = url.set(query=query)
            options["connect_args"] = {"timeout": 10, "command_timeout": 15}
            options["pool_size"] = 3
            options["max_overflow"] = 2
            dialect = "postgresql"
        elif url.drivername == "sqlite+aiosqlite" and os.getenv("AUTH_DATABASE_URL") and not os.getenv("RENDER"):
            dialect = "sqlite"
            options["execution_options"] = {"schema_translate_map": {AUTH_SCHEMA: None}}
        else:
            return False
        engine = create_async_engine(url, **options)
        async with engine.begin() as connection:
            if dialect == "postgresql":
                await connection.execute(CreateSchema(AUTH_SCHEMA, if_not_exists=True))
            await connection.run_sync(Base.metadata.create_all)
        _engine = engine
        _sessions = async_sessionmaker(engine, expire_on_commit=False)
        _dialect = dialect
        _daily_limit = limit
        cookie_transport.cookie_secure = _cookie_secure()
        auth_configuration_error = None
        return True
    except Exception:
        if engine is not None:
            try:
                await engine.dispose()
            except (SQLAlchemyError, OSError, TimeoutError):
                pass
        return False


async def close_auth():
    global _engine, _sessions, _dialect, auth_configuration_error
    engine, _engine = _engine, None
    _sessions = None
    _dialect = None
    auth_configuration_error = UNAVAILABLE_DETAIL
    if engine is not None:
        try:
            await engine.dispose()
        except (SQLAlchemyError, OSError, TimeoutError):
            pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    sessions = _sessions
    if not auth_configured() or sessions is None:
        raise HTTPException(503, UNAVAILABLE_DETAIL)
    try:
        async with sessions() as session:
            yield session
    except (SQLAlchemyError, OSError, TimeoutError):
        raise HTTPException(503, UNAVAILABLE_DETAIL) from None


async def get_user_db(session: AsyncSession = Depends(get_session)):
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)


async def get_strategy(session: AsyncSession = Depends(get_session)):
    return HashedDatabaseStrategy(
        SQLAlchemyAccessTokenDatabase(session, AccessToken),
        lifetime_seconds=SESSION_LIFETIME_SECONDS,
    )


cookie_transport = CookieTransport(
    cookie_name=COOKIE_NAME,
    cookie_max_age=SESSION_LIFETIME_SECONDS,
    cookie_secure=_cookie_secure(),
    cookie_httponly=True,
    cookie_samesite="lax",
    cookie_path="/",
)
auth_backend = AuthenticationBackend(
    name="user_session", transport=cookie_transport, get_strategy=get_strategy
)
fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])
router = APIRouter(prefix="/api/auth", tags=["User accounts"])
router.include_router(fastapi_users.get_register_router(UserRead, UserCreate))
router.include_router(fastapi_users.get_auth_router(auth_backend))


@router.get("/status")
async def status():
    return {"configured": auth_configured()}


@router.get("/me", response_model=UserRead)
async def me(request: Request):
    if not auth_configured():
        raise HTTPException(503, UNAVAILABLE_DETAIL)
    try:
        user = await resolve_session(request.scope)
    except AuthUnavailableError:
        raise HTTPException(503, UNAVAILABLE_DETAIL) from None
    if user is None:
        raise HTTPException(401, "Sign in to continue")
    return user


async def resolve_session(scope) -> dict[str, str] | None:
    """Validate an opaque cookie and the current active account from the DB."""
    try:
        cookie = SimpleCookie()
        for key, value in scope.get("headers", []):
            if key.lower() == b"cookie":
                cookie.load(value.decode("latin-1"))
        morsel = cookie.get(COOKIE_NAME)
        if morsel is None or len(morsel.value) != 43:
            return None
    except (CookieError, UnicodeError):
        return None
    sessions = _sessions
    if not auth_configured() or sessions is None:
        raise AuthUnavailableError(UNAVAILABLE_DETAIL)
    try:
        async with sessions() as session:
            manager = UserManager(SQLAlchemyUserDatabase(session, User))
            strategy = HashedDatabaseStrategy(
                SQLAlchemyAccessTokenDatabase(session, AccessToken), SESSION_LIFETIME_SECONDS
            )
            user = await strategy.read_token(morsel.value, manager)
            if user is None or not user.is_active:
                return None
            return {"id": str(user.id), "email": user.email}
    except (SQLAlchemyError, OSError, TimeoutError):
        raise AuthUnavailableError(UNAVAILABLE_DETAIL) from None


async def reserve_analysis(user_id: str) -> bool:
    """Atomically reserve one analysis in the user's durable UTC-day allowance."""
    sessions, dialect = _sessions, _dialect
    if not auth_configured() or sessions is None:
        raise AuthUnavailableError(UNAVAILABLE_DETAIL)
    try:
        user_uuid = uuid.UUID(user_id)
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        statement = insert(DailyAnalysisUsage).values(
            user_id=user_uuid, day=datetime.now(timezone.utc).date(), used=1
        )
        statement = statement.on_conflict_do_update(
            index_elements=[DailyAnalysisUsage.user_id, DailyAnalysisUsage.day],
            set_={"used": DailyAnalysisUsage.used + 1},
            where=DailyAnalysisUsage.used < _daily_limit,
        ).returning(DailyAnalysisUsage.used)
        async with sessions() as session:
            count = (await session.execute(statement)).scalar_one_or_none()
            await session.commit()
            return count is not None
    except (SQLAlchemyError, OSError, TimeoutError, ValueError):
        raise AuthUnavailableError(UNAVAILABLE_DETAIL) from None
