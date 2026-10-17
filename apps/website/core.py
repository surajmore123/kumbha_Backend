"""Plumbing shared by every website endpoint: JSON errors, tokens and OTP hashing, rate limits, and the
`endpoint` decorator that parses/validates requests with the pydantic schemas."""

import functools
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import BaseModel, TypeAdapter, ValidationError

from .conf import get_settings

log = logging.getLogger("apps.website")
User = get_user_model()

# ───────────────────────── errors ─────────────────────────


class AppError(Exception):
    """Becomes {"error": {"code", "message", ...extra}} with the given HTTP status."""

    def __init__(self, status: int, code: str, message: str, **extra):
        self.status, self.code, self.message, self.extra = status, code, message, extra


def _json(status: int, body: Any, headers: dict[str, str] | None = None) -> HttpResponse:
    resp = HttpResponse(json.dumps(body, ensure_ascii=False, separators=(",", ":")), status=status, content_type="application/json")
    for k, v in (headers or {}).items():
        resp[k] = v
    return resp


def error_response(exc: AppError) -> HttpResponse:
    headers = {"Retry-After": str(exc.extra["retry_after"])} if "retry_after" in exc.extra else None
    return _json(exc.status, {"error": {"code": exc.code, "message": exc.message, **exc.extra}}, headers)


# ───────────────────────── security ─────────────────────────


def utcnow() -> datetime:
    return datetime.now(UTC)


def generate_otp(length: int) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def hash_otp(phone: str, code: str) -> str:
    """Keyed hash so a database leak does not reveal live codes."""
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"otp:{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def verify_otp_hash(phone: str, code: str, expected: str) -> bool:
    return hmac.compare_digest(hash_otp(phone, code), expected)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def anonymize_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"ip:{ip}".encode(), hashlib.sha256).hexdigest()[:32]


def create_access_token(user_id: str, role: str) -> tuple[str, int]:
    s = get_settings()
    expires_in = s.access_token_minutes * 60
    now = utcnow()
    payload = {"sub": user_id, "role": role, "type": "access", "iat": now, "exp": now + timedelta(seconds=expires_in)}
    return jwt.encode(payload, s.secret_key, algorithm=s.jwt_algorithm), expires_in


def decode_access_token(token: str) -> dict:
    s = get_settings()
    payload = jwt.decode(token, s.secret_key, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub"]})
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


# ───────────────────────── admin panel accounts ─────────────────────────

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    """scrypt with a random salt, stored as scrypt$<salt hex>$<hash hex>."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, expected = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), dklen=32, **_SCRYPT)
    return hmac.compare_digest(digest.hex(), expected)


def create_admin_token(admin_id: str, token_version: int) -> tuple[str, int]:
    """Admin panel session. Its own token type, so a website/app user's token can never open the admin API."""
    s = get_settings()
    expires_in = s.admin_session_hours * 3600
    now = utcnow()
    payload = {"sub": admin_id, "ver": token_version, "type": "admin", "iat": now, "exp": now + timedelta(seconds=expires_in)}
    return jwt.encode(payload, s.secret_key, algorithm=s.jwt_algorithm), expires_in


def decode_admin_token(token: str) -> dict:
    s = get_settings()
    payload = jwt.decode(token, s.secret_key, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub"]})
    if payload.get("type") != "admin":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


# ───────────────────────── users (shared with the mobile app) ─────────────────────────


def user_id_str(user) -> str:
    """Website ids are 32 hex chars (the old backend's format); the Django user id is the same UUID."""
    return user.user_id.hex


def user_by_id(raw: str):
    try:
        return User.objects.filter(user_id=uuid.UUID(hex=raw[:32])).first()
    except ValueError:
        return None


def app_phone(phone10: str) -> str:
    """The mobile app stores numbers as +91XXXXXXXXXX."""
    return f"+91{phone10}"


def website_phone(user) -> str | None:
    p = (user.phone_number or "").replace(" ", "")
    if p.startswith("+91"):
        p = p[3:]
    elif len(p) == 12 and p.startswith("91"):
        p = p[2:]
    return p or None


def user_by_phone(phone10: str):
    return User.objects.filter(phone_number__in=[app_phone(phone10), phone10, f"91{phone10}"]).first()


def user_out(user) -> dict:
    return {
        "id": user_id_str(user),
        "phone": website_phone(user),
        "email": user.email,
        "name": user.full_Name,
        "role": user.role,
        "preferred_language": user.preferred_language,
        "created_at": user.created_at,
    }


# ───────────────────────── rate limits ─────────────────────────


class MemoryLimiter:
    def __init__(self) -> None:
        self._store: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            count, reset = self._store.get(key, (0, now + window))
            if now >= reset:
                count, reset = 0, now + window
            count += 1
            self._store[key] = (count, reset)
            if len(self._store) > 50_000:
                self._store = {k: v for k, v in self._store.items() if v[1] > now}
        return count <= limit, max(1, int(reset - now))

    def reset(self) -> None:
        self._store.clear()


class RedisLimiter:
    def __init__(self, url: str) -> None:
        from redis import Redis

        self._redis = Redis.from_url(url, decode_responses=True, socket_timeout=2)

    def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        k = f"kpweb:rl:{key}"
        pipe = self._redis.pipeline(transaction=True)
        count, ttl = pipe.incr(k).ttl(k).execute()
        if ttl < 0:
            self._redis.expire(k, window)
            ttl = window
        return count <= limit, max(1, ttl)


_limiter = None


def get_limiter():
    global _limiter
    if _limiter is None:
        url = get_settings().redis_url
        _limiter = RedisLimiter(url) if url else MemoryLimiter()
    return _limiter


def enforce(key: str, limit: int, window: int) -> None:
    allowed, retry_after = get_limiter().hit(key, limit, window)
    if not allowed:
        raise AppError(429, "rate_limited", "Too many requests. Please wait and try again.", retry_after=retry_after)


def client_ip(request: HttpRequest) -> str:
    # nginx overwrites X-Real-IP with the real visitor address (Cloudflare-aware), so clients can't spoof it.
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or "unknown"


# ───────────────────────── the endpoint decorator ─────────────────────────

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Resource-Policy": "same-site",
}


class Ctx:
    """What a handler gets: the request, the signed-in user or admin (or None), parsed body/query/path."""

    def __init__(self, request: HttpRequest):
        self.request = request
        self.user = None
        self.admin = None  # AdminAccount on auth="admin" endpoints
        self.body: Any = None
        self.query: Any = None
        self.headers: dict[str, str] = {}
        self.ip = client_ip(request)
        self.user_agent = request.META.get("HTTP_USER_AGENT")


def _user_from_header(request: HttpRequest):
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        payload = decode_access_token(token.strip())
    except jwt.PyJWTError as exc:
        raise AppError(401, "invalid_token", "Your session has expired. Please sign in again.") from exc
    user = user_by_id(str(payload["sub"]))
    if user is None or not user.is_active:
        raise AppError(401, "invalid_token", "Please sign in again.")
    return user


def _admin_from_header(request: HttpRequest):
    """Admin panel accounts only: website/app user tokens (whatever their role) are refused."""
    from .models import AdminAccount

    scheme, _, token = request.META.get("HTTP_AUTHORIZATION", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AppError(401, "not_authenticated", "Please sign in to the admin panel.")
    try:
        payload = decode_admin_token(token.strip())
    except jwt.PyJWTError as exc:
        raise AppError(401, "invalid_token", "Your admin session has ended. Please sign in again.") from exc
    admin = AdminAccount.objects.filter(pk=str(payload["sub"])[:32]).first()
    if admin is None or not admin.is_active or admin.token_version != payload.get("ver"):
        raise AppError(401, "invalid_token", "Your admin session has ended. Please sign in again.")
    return admin


def _parse(adapter: TypeAdapter, data: Any, loc: str | None = None) -> Any:
    try:
        return adapter.validate_python(data)
    except ValidationError as exc:
        raise _Invalid(exc, loc) from exc


class _Invalid(Exception):
    def __init__(self, exc: ValidationError, loc: str | None):
        self.exc, self.loc = exc, loc


def _query_dict(request: HttpRequest) -> dict[str, str]:
    return {k: request.GET.get(k) for k in request.GET.keys()}


def endpoint(
    *,
    auth: str | None = None,
    body: type[BaseModel] | None = None,
    query: type | None = None,
    path: dict[str, Any] | None = None,
    limit: tuple[str, int] | None = None,
    status: int = 200,
    max_body: int | None = None,
):
    """Turn `handler(ctx, **path_params)` into a Django view.

    auth: None (anonymous), "optional", "user" (website/app user in ctx.user) or "admin" (admin panel account
    in ctx.admin). body/query: pydantic models (query may also be a dict of {name: type}). path: {name: type}
    to validate URL parts. limit: (name, per_minute) per IP. max_body: bytes allowed in the request body when
    an endpoint needs more than the usual limit (image upload). The handler returns a pydantic model, a list
    of them, a dict, an HttpResponse (sent as is), or None (204).
    """
    body_adapter = TypeAdapter(body) if body else None
    query_adapter = TypeAdapter(query) if isinstance(query, type) else None
    query_fields = {k: TypeAdapter(t) for k, t in query.items()} if isinstance(query, dict) else None
    path_adapters = {k: TypeAdapter(t) for k, t in (path or {}).items()}

    def decorator(fn):
        @functools.wraps(fn)
        def view(request: HttpRequest, **kwargs) -> HttpResponse:
            rid = (request.META.get("HTTP_X_REQUEST_ID") or "")[:64]
            rid = rid if rid and rid.replace("-", "").isalnum() else uuid.uuid4().hex
            try:
                resp = _run(request, kwargs)
            except AppError as exc:
                resp = error_response(exc)
            except _Invalid as inv:
                fields = [
                    {"field": ".".join(str(p) for p in ((inv.loc,) if inv.loc else ()) + tuple(e["loc"])), "message": e["msg"]}
                    for e in inv.exc.errors()
                ]
                resp = _json(422, {"error": {"code": "validation_error", "message": "Some fields are invalid.", "fields": fields}})
            except Exception:  # noqa: BLE001
                log.exception("unhandled error", extra={"path": request.path})
                resp = _json(500, {"error": {"code": "internal_error", "message": "Something went wrong. Please try again."}})
            resp["X-Request-ID"] = rid
            for k, v in SECURITY_HEADERS.items():
                if not resp.has_header(k):  # a handler may loosen one on purpose (e.g. images for other sites)
                    resp[k] = v
            if get_settings().is_prod:
                resp["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            return resp

        def _run(request: HttpRequest, kwargs: dict) -> HttpResponse:
            s = get_settings()
            ctx = Ctx(request)
            body_limit = max_body or s.max_body_bytes
            declared = request.META.get("CONTENT_LENGTH")
            if declared and declared.isdigit() and int(declared) > body_limit:
                raise AppError(413, "payload_too_large", "Request body is too large.")

            # Same order as the old FastAPI app: route rate limit, sign-in, then path/query/body validation.
            if limit:
                enforce(f"{limit[0]}:{ctx.ip}", limit[1], 60)
            if auth == "admin":
                ctx.admin = _admin_from_header(request)
            elif auth:
                ctx.user = _user_from_header(request)
                if auth == "user" and ctx.user is None:
                    raise AppError(401, "not_authenticated", "Please sign in.")
            for name, adapter in path_adapters.items():
                kwargs[name] = _parse(adapter, kwargs[name], name)
            if query_adapter:
                ctx.query = _parse(query_adapter, _query_dict(request))
            elif query_fields:
                raw = _query_dict(request)
                ctx.query = {}
                for name, adapter in query_fields.items():
                    if name in raw:
                        ctx.query[name] = _parse(adapter, raw[name], name)
            if body_adapter:
                if len(request.body) > s.max_body_bytes:
                    raise AppError(413, "payload_too_large", "Request body is too large.")
                try:
                    data = json.loads(request.body or b"null")
                except ValueError as exc:
                    pos = str(getattr(exc, "pos", ""))
                    raise AppError(422, "validation_error", "Some fields are invalid.", fields=[{"field": pos, "message": "JSON decode error"}]) from None
                if data is None:
                    raise AppError(422, "validation_error", "Some fields are invalid.", fields=[{"field": "", "message": "Field required"}])
                ctx.body = _parse(body_adapter, data)

            result = fn(ctx, **kwargs)
            if result is None:
                return HttpResponse(status=204)
            if isinstance(result, HttpResponse):
                return result
            if isinstance(result, BaseModel):
                content = result.model_dump_json()
            elif isinstance(result, list) and all(isinstance(r, BaseModel) for r in result):
                content = "[" + ",".join(r.model_dump_json() for r in result) + "]"
            else:
                content = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
            resp = HttpResponse(content, status=status, content_type="application/json")
            for k, v in ctx.headers.items():
                resp[k] = v
            return resp

        return csrf_exempt(view)

    return decorator


def global_limit(request: HttpRequest) -> HttpResponse | None:
    """Coarse per-IP limit on every website API call (404s and 405s included); returns a 429 or None."""
    allowed, retry_after = get_limiter().hit(f"global:{client_ip(request)}", get_settings().rate_limit_per_minute, 60)
    if not allowed:
        body = {"error": {"code": "rate_limited", "message": "Too many requests. Please wait and try again."}}
        return _json(429, body, {"Retry-After": str(retry_after)})
    return None


def methods(**handlers):
    """One URL, several HTTP methods: methods(get=view_a, post=view_b)."""

    def view(request: HttpRequest, **kwargs) -> HttpResponse:
        if (limited := global_limit(request)) is not None:
            return limited
        handler = handlers.get(request.method.lower())
        if handler is None:
            return _json(405, {"error": {"code": "http_error", "message": "Method Not Allowed"}}, {"Allow": ", ".join(m.upper() for m in handlers)})
        return handler(request, **kwargs)

    return csrf_exempt(view)
