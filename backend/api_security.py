"""Process-local API access, admission limits, and shared downstream-call budgets."""
from __future__ import annotations

import hmac
import hashlib
import json
import math
import os
import re
import threading
import time
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass, field
from urllib.parse import parse_qs

from starlette.responses import JSONResponse
from fastapi.exception_handlers import request_validation_exception_handler

MAX_BODY_BYTES = 256 * 1024
MAX_PROVIDER_CALLS = 32
MAX_WORK_SECONDS = 180
AUTH_PATHS = {"/api/auth/login", "/api/auth/register", "/api/auth/logout", "/api/auth/me", "/api/auth/status"}
USER_ANALYSIS_PATHS = re.compile(
    r"/api/(?:chatbot/query|perspective/simulate|(?:polar/)?(?:intelligence-brief|ai-analysis)"
    r"|network/intelligence/(?:analyze|narrative/[^/]+/analyze)"
    r"|stream/api/(?:media-brief|analyze-event|extract-topics|topic-analysis)"
    r"|globe/events/(?:news|headline-analysis|ai-analysis|[^/]+/(?:analyze|news-analysis|ai-analysis)))"
)


def user_analysis_allowed(path, method):
    # Collection and future writes stay private unless deliberately added here.
    return method == "POST" and USER_ANALYSIS_PATHS.fullmatch(path) is not None


def _csrf_valid(headers):
    if headers.get(b"x-narrative-csrf") != b"1":
        return False
    origin = headers.get(b"origin", b"").decode("latin-1")
    allowed = os.getenv("FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    # Non-browser clients may omit Origin but must still send the custom header.
    return not origin or origin in {v.strip() for v in allowed.split(",") if v.strip()}


async def api_validation_error(request, exc):
    if request.url.path.startswith("/api/auth/"):
        # Pydantic normally echoes rejected inputs, including passwords.
        details = [{key: error[key] for key in ("loc", "msg", "type") if key in error} for error in exc.errors()]
        return JSONResponse({"detail": details}, status_code=422, headers={"Cache-Control": "no-store"})
    return await request_validation_exception_handler(request, exc)


class WorkLimitExceeded(RuntimeError):
    pass


@dataclass
class WorkBudget:
    remaining: int = MAX_PROVIDER_CALLS
    deadline: float = field(default_factory=lambda: time.monotonic() + MAX_WORK_SECONDS)
    exhausted: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def consume(self):
        with self.lock:
            if self.remaining <= 0 or time.monotonic() >= self.deadline:
                self.exhausted = True
                raise WorkLimitExceeded("Request provider-call or time budget exceeded")
            self.remaining -= 1


_work_budget: ContextVar[WorkBudget | None] = ContextVar("narrative_work_budget", default=None)


def consume_provider_call():
    """Reserve before each outbound attempt, including fallbacks and retries.

    Async children and sync handler threads share the same locked budget object.
    CLI jobs outside an HTTP request retain their own existing execution policy.
    """
    budget = _work_budget.get()
    if budget is not None:
        budget.consume()


def count_httpx_redirect(request):
    """Callers reserve the first attempt; HTTPX copies extensions on redirects."""
    if request.extensions.get("narrative_attempt_reserved"):
        consume_provider_call()
    request.extensions["narrative_attempt_reserved"] = True


async def count_async_httpx_redirect(request):
    count_httpx_redirect(request)


def work_budget_active():
    return _work_budget.get() is not None


def ensure_work_budget():
    budget = _work_budget.get()
    if budget is not None and budget.exhausted:
        raise WorkLimitExceeded("Request provider-call or time budget exceeded")


def _bounded_json(value, depth=0):
    if depth > 12:
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, str):
        return len(value) <= 8000
    if isinstance(value, list):
        return len(value) <= 512 and all(_bounded_json(v, depth + 1) for v in value)
    if isinstance(value, dict):
        return len(value) <= 128 and all(len(k) <= 128 and _bounded_json(v, depth + 1) for k, v in value.items())
    return True


class APISecurityMiddleware:
    """Fail closed for work; bound every API route, including mount aliases.

    Counters are intentionally per process. Run one worker until a shared admission
    store/queue is installed. Forwarded IP headers are not trusted here.
    """

    def __init__(self, app, standalone=False, read_limit=None, work_limit=None, concurrency=2, window=None,
                 user_authenticator=None, analysis_reserver=None):
        self.app = app
        self.standalone = standalone
        self.read_limit = read_limit if read_limit is not None else int(os.getenv("RATE_LIMIT_MAX", "60"))
        self.work_limit = work_limit if work_limit is not None else int(os.getenv("WORK_LIMIT_MAX", "10"))
        self.window = window if window is not None else int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
        if min(self.read_limit, self.work_limit, self.window, concurrency) < 1:
            raise ValueError("API limits must be positive")
        self.concurrency = concurrency
        self.active = 0
        self.read_buckets = OrderedDict()
        self.work_bucket = []
        self.lock = threading.Lock()
        self.user_authenticator = user_authenticator
        self.analysis_reserver = analysis_reserver
        self.auth_buckets = OrderedDict()
        self.auth_global = []
        self.auth_active = 0
        self.user_work_buckets = OrderedDict()

    @staticmethod
    def _prune(buckets, now, window):
        for key in list(buckets):
            values = [t for t in buckets[key] if now - t < window]
            if values:
                buckets[key] = values
            else:
                del buckets[key]

    @staticmethod
    def _record(buckets, key, now):
        buckets.setdefault(key, []).append(now)
        buckets.move_to_end(key)
        while len(buckets) > 4096:
            buckets.popitem(last=False)

    @staticmethod
    def _group(path):
        segment = path.split("/", 3)[2] if path.startswith("/api/") else "chatbot"
        return segment if segment in {"globe", "network", "stream", "chatbot", "perspective"} else "polar"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("narrative_security_checked"):
            return await self.app(scope, receive, send)
        path, method = scope["path"], scope["method"]
        protected_path = self.standalone or path == "/api" or path.startswith("/api/") or path == "/diag"
        if not protected_path or method == "OPTIONS":
            return await self.app(scope, receive, send)
        work = method not in {"GET", "HEAD"}
        auth_route = path in AUTH_PATHS
        needs_auth = (work or path == "/diag") and not auth_route
        headers = dict(scope.get("headers", []))
        principal = None
        operator = False

        async def reject(status, detail):
            headers = {"Retry-After": str(self.window)} if status == 429 else {}
            if status == 401:
                headers["WWW-Authenticate"] = "Bearer"
            headers["Cache-Control"] = "no-store"
            await JSONResponse({"detail": detail}, status_code=status, headers=headers)(scope, receive, send)

        if needs_auth:
            expected = os.getenv("NARRATIVE_API_TOKEN", "")
            provided = headers.get(b"authorization", b"").decode("latin-1")
            scheme, _, token = provided.partition(" ")
            configured = len(expected) >= 32 and expected.strip() == expected
            operator = configured and scheme.lower() == "bearer" and hmac.compare_digest(token.encode(), expected.encode())
            if not operator:
                if provided:
                    if not configured:
                        return await reject(503, "Operator access is not configured")
                    return await reject(401, "A valid operator bearer token is required")
                if self.user_authenticator:
                    try:
                        principal = await self.user_authenticator(scope)
                    except Exception:
                        return await reject(503, "User authentication is temporarily unavailable")
                if not principal:
                    if not configured and not self.user_authenticator:
                        return await reject(503, "Operator access is not configured; set NARRATIVE_API_TOKEN (at least 32 characters)")
                    return await reject(401, "Sign in to run analysis")
                if not user_analysis_allowed(path, method):
                    return await reject(403, "This action requires administrator access")
                if not _csrf_valid(headers):
                    return await reject(403, "Request origin or CSRF header is invalid")
                scope["narrative_user_id"] = principal["id"]

        if auth_route and work and not _csrf_valid(headers):
            return await reject(403, "Request origin or CSRF header is invalid")

        now = time.monotonic()
        client = (scope.get("client") or ("unknown", 0))[0]
        key = (principal["id"] if principal else client, self._group(path))
        with self.lock:
            # LRU cap plus expiry prevent arbitrary client addresses growing memory.
            for old_key in list(self.read_buckets):
                bucket = [t for t in self.read_buckets[old_key] if now - t < self.window]
                if bucket:
                    self.read_buckets[old_key] = bucket
                else:
                    del self.read_buckets[old_key]
            bucket = self.read_buckets.get(key, [])
            throttled = len(bucket) >= self.read_limit
            if not throttled:
                bucket.append(now)
                self.read_buckets[key] = bucket
                self.read_buckets.move_to_end(key)
                while len(self.read_buckets) > 4096:
                    self.read_buckets.popitem(last=False)
        if throttled:
            return await reject(429, "API request rate limit exceeded")

        body = bytearray()
        if work:
            # Check the actual stream, not only the optional Content-Length header.
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                maximum = 16 * 1024 if auth_route else MAX_BODY_BYTES
                if len(body) + len(chunk) > maximum:
                    return await reject(413, "Request body exceeds limit")
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
            login_form = auth_route and path == "/api/auth/login"
            if body and not login_form:
                try:
                    payload = json.loads(body)
                except (ValueError, RecursionError):
                    return await reject(422, "Request body must be valid JSON")
                if not _bounded_json(payload):
                    return await reject(422, "Request JSON exceeds nesting, text, or collection limits")
            now = time.monotonic()
            if auth_route:
                if login_form:
                    content_type = headers.get(b"content-type", b"").decode("latin-1").partition(";")[0].strip().lower()
                    if content_type != "application/x-www-form-urlencoded":
                        return await reject(415, "Sign-in requires a URL-encoded form")
                    try:
                        fields = parse_qs(body.decode("utf-8"), max_num_fields=16, keep_blank_values=True, strict_parsing=True)
                        if any(len(values) != 1 for values in fields.values()):
                            return await reject(422, "Sign-in fields must not be repeated")
                        account = fields.get("username", [""])[0]
                    except (ValueError, UnicodeError):
                        return await reject(422, "Invalid sign-in form")
                else:
                    account = payload.get("email", "") if body and isinstance(payload, dict) else ""
                try:
                    account = hashlib.sha256(str(account).strip().casefold().encode()).hexdigest()
                except UnicodeError:
                    return await reject(422, "Invalid account details")
                with self.lock:
                    self._prune(self.auth_buckets, now, 300)
                    self.auth_global = [t for t in self.auth_global if now - t < 60]
                    keys = [("client", client)]
                    if path in {"/api/auth/login", "/api/auth/register"}:
                        keys.append(("account", account))
                    admitted = self.auth_active < 1 and len(self.auth_global) < 30 and all(len(self.auth_buckets.get(k, [])) < 10 for k in keys)
                    if admitted:
                        self.auth_active += 1
                        self.auth_global.append(now)
                        for auth_key in keys:
                            self._record(self.auth_buckets, auth_key, now)
                if not admitted:
                    return await reject(429, "Too many sign-in attempts. Try again later")
            else:
                with self.lock:
                    self.work_bucket = [t for t in self.work_bucket if now - t < self.window]
                    self._prune(self.user_work_buckets, now, self.window)
                    user_key = principal["id"] if principal else None
                    user_limited = user_key is not None and len(self.user_work_buckets.get(user_key, [])) >= 3
                    admitted = not user_limited and self.active < self.concurrency and len(self.work_bucket) < self.work_limit
                    if admitted:
                        self.active += 1
                        self.work_bucket.append(now)
                        if user_key:
                            self._record(self.user_work_buckets, user_key, now)
                if not admitted:
                    return await reject(429, "Analysis rate or concurrency limit exceeded")

        async def replay():
            nonlocal body
            if body is not None:
                value, body = bytes(body), None
                return {"type": "http.request", "body": value, "more_body": False}
            return await receive()

        budget = WorkBudget() if work and not auth_route else None
        context_token = _work_budget.set(budget)
        replaced = False
        response_started = False

        async def bounded_send(message):
            nonlocal replaced, response_started
            if message["type"] == "http.response.start":
                response_started = True
                if auth_route or principal:
                    response_headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                    message = {**message, "headers": response_headers + [(b"cache-control", b"no-store")]}
            if message["type"] == "http.response.start" and budget and budget.exhausted:
                replaced = True
                await JSONResponse({"detail": "Request provider-call or time budget exceeded"}, status_code=429, headers={"Retry-After": str(self.window)})(scope, replay, send)
            elif not replaced:
                await send(message)

        scope["narrative_security_checked"] = True
        try:
            if work and principal:
                if self.analysis_reserver is None:
                    return await reject(503, "User analysis limits are unavailable")
                try:
                    allowed = await self.analysis_reserver(principal["id"])
                except Exception:
                    return await reject(503, "User analysis limits are temporarily unavailable")
                if not allowed:
                    return await reject(429, "Daily analysis limit reached. Try again tomorrow")
            # Await includes Starlette background tasks: the slot remains reserved.
            await self.app(scope, replay if work else receive, bounded_send)
        except WorkLimitExceeded:
            if not response_started:
                await reject(429, "Request provider-call or time budget exceeded")
            elif not replaced:
                raise
        finally:
            _work_budget.reset(context_token)
            if work:
                with self.lock:
                    if auth_route:
                        self.auth_active -= 1
                    else:
                        self.active -= 1
