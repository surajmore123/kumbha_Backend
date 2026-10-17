"""Website sign-in: mobile OTP or Google, then short-lived access tokens + rotating refresh tokens.

Accounts are the shared Django users: signing in with a mobile number that already uses the app gives
the same account (matched on +91XXXXXXXXXX), and a Google sign-in is matched on email."""

from datetime import timedelta

from django.db import transaction

from ..conf import get_settings
from ..core import (
    AppError,
    User,
    anonymize_ip,
    app_phone,
    create_access_token,
    endpoint,
    enforce,
    generate_otp,
    hash_otp,
    hash_token,
    new_refresh_token,
    user_by_phone,
    user_id_str,
    user_out,
    utcnow,
    verify_otp_hash,
)
from ..integrations import get_sms_sender, verify_google_credential
from ..models import OtpChallenge, PhoneLock, RefreshToken
from ..schemas import GoogleSignIn, Message, OtpRequest, OtpRequested, OtpVerify, ProfileUpdate, RefreshIn, TokenPair, UserOut


def _ensure_not_locked(phone: str) -> None:
    lock = PhoneLock.objects.filter(phone=phone).first()
    if lock and lock.locked_until > utcnow():
        retry = int((lock.locked_until - utcnow()).total_seconds()) + 1
        raise AppError(423, "otp_locked", "Too many wrong codes. Sign-in is paused for this number.", retry_after=retry)


def issue_tokens(user, user_agent: str | None) -> TokenPair:
    s = get_settings()
    access, expires_in = create_access_token(user_id_str(user), user.role)
    refresh = new_refresh_token()
    RefreshToken.objects.create(
        user=user,
        token_hash=hash_token(refresh),
        expires_at=utcnow() + timedelta(days=s.refresh_token_days),
        user_agent=(user_agent or "")[:200],
    )
    user.refresh_from_db()
    return TokenPair(access_token=access, refresh_token=refresh, expires_in=expires_in, user=UserOut(**user_out(user)))


@endpoint(body=OtpRequest, limit=("otp-request", 10))
def request_otp(ctx):
    """Send a one-time code by SMS. Limited per number (resend gap + daily cap) and per IP."""
    s = get_settings()
    phone = ctx.body.phone
    _ensure_not_locked(phone)
    enforce(f"otp-resend:{phone}", 1, s.otp_resend_seconds)
    enforce(f"otp-daily:{phone}", s.otp_daily_limit, 86_400)
    enforce(f"otp-ip:{ctx.ip}", 20, 3_600)

    code = generate_otp(s.otp_length)
    with transaction.atomic():
        # Only the newest code is valid.
        OtpChallenge.objects.filter(phone=phone, consumed_at__isnull=True).update(consumed_at=utcnow())
        OtpChallenge.objects.create(
            phone=phone,
            code_hash=hash_otp(phone, code),
            expires_at=utcnow() + timedelta(seconds=s.otp_ttl_seconds),
            ip_hash=anonymize_ip(ctx.ip),
        )
        sender = get_sms_sender()
        sender.send_otp(phone, code)
    debug = code if (s.env != "prod" and sender.name == "console") else None
    return OtpRequested(expires_in=s.otp_ttl_seconds, resend_in=s.otp_resend_seconds, debug_code=debug)


@endpoint(body=OtpVerify, limit=("otp-verify", 20))
def verify_otp(ctx):
    """Exchange a correct code for tokens. 3 wrong codes lock the number for 15 minutes."""
    s = get_settings()
    phone, code = ctx.body.phone, ctx.body.code
    _ensure_not_locked(phone)
    with transaction.atomic():
        challenge = (
            OtpChallenge.objects.select_for_update()
            .filter(phone=phone, consumed_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if not challenge or challenge.expires_at < utcnow():
            raise AppError(400, "otp_expired", "This code has expired. Please request a new one.")

        if not verify_otp_hash(phone, code, challenge.code_hash):
            challenge.attempts += 1
            left = s.otp_max_attempts - challenge.attempts
            if left <= 0:
                challenge.consumed_at = utcnow()
                challenge.save(update_fields=["attempts", "consumed_at", "updated_at"])
                PhoneLock.objects.update_or_create(phone=phone, defaults={"locked_until": utcnow() + timedelta(minutes=s.otp_lock_minutes)})
                error = AppError(423, "otp_locked", "Too many wrong codes. Sign-in is paused for this number.", retry_after=s.otp_lock_minutes * 60)
            else:
                challenge.save(update_fields=["attempts", "updated_at"])
                error = AppError(400, "otp_invalid", "The code doesn't match. Please check and try again.", attempts_left=left)
        else:
            error = None
            challenge.consumed_at = utcnow()
            challenge.save(update_fields=["consumed_at", "updated_at"])
    if error:  # raised outside the transaction so the attempt count / lock is saved
        raise error

    user = user_by_phone(phone)
    if user is None:
        user = User.objects.create(phone_number=app_phone(phone), role="user", is_active=True, otp_verified=True)
    if user.is_active is False:
        raise AppError(403, "account_disabled", "This account is disabled.")
    user.last_login = utcnow()
    user.otp_verified = True
    user.save(update_fields=["last_login", "otp_verified", "updated_at"])
    return issue_tokens(user, ctx.user_agent)


@endpoint(body=GoogleSignIn, limit=("google", 20))
def google(ctx):
    """Exchange a Google ID token (from "Sign in with Google") for Kumbh Path tokens."""
    claims = verify_google_credential(ctx.body.credential)
    user = User.objects.filter(email__iexact=claims["email"]).first()
    if user is None:
        user = User.objects.create(email=claims["email"], full_Name=(claims.get("name") or "")[:80] or None, role="user", is_active=True)
    if user.is_active is False:
        raise AppError(403, "account_disabled", "This account is disabled.")
    if not user.full_Name and claims.get("name"):
        user.full_Name = claims["name"][:80]
    user.last_login = utcnow()
    user.save(update_fields=["full_Name", "last_login", "updated_at"])
    return issue_tokens(user, ctx.user_agent)


@endpoint(body=RefreshIn, limit=("refresh", 30))
def refresh(ctx):
    with transaction.atomic():
        row = RefreshToken.objects.select_for_update().filter(token_hash=hash_token(ctx.body.refresh_token)).first()
        if row is None:
            raise AppError(401, "invalid_token", "Please sign in again.")
        if row.revoked_at is not None:
            reused = True
        else:
            reused = False
            if row.expires_at < utcnow():
                raise AppError(401, "token_expired", "Please sign in again.")
            row.revoked_at = utcnow()
            row.save(update_fields=["revoked_at", "updated_at"])
    if reused:
        # A rotated token was used again: likely stolen. End every session for this user.
        RefreshToken.objects.filter(user_id=row.user_id, revoked_at__isnull=True).update(revoked_at=utcnow())
        raise AppError(401, "token_reused", "Your session ended for safety. Please sign in again.")
    user = User.objects.filter(pk=row.user_id).first()
    if user is None or not user.is_active:
        raise AppError(401, "invalid_token", "Please sign in again.")
    return issue_tokens(user, ctx.user_agent)


@endpoint(body=RefreshIn)
def logout(ctx):
    RefreshToken.objects.filter(token_hash=hash_token(ctx.body.refresh_token), revoked_at__isnull=True).update(revoked_at=utcnow())
    return Message(message="Signed out")


@endpoint(auth="user")
def me(ctx):
    return UserOut(**user_out(ctx.user))


@endpoint(auth="user", body=ProfileUpdate)
def update_me(ctx):
    data = ctx.body.model_dump(exclude_none=True)
    user = ctx.user
    if "name" in data:
        user.full_Name = data["name"]
    if "preferred_language" in data:
        user.preferred_language = data["preferred_language"]
    user.save()
    return UserOut(**user_out(user))
