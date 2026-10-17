"""Admin panel sign-in and admin accounts. Separate from website/app users (no OTP, no Google): each admin
has a username + password, and admins add each other from the panel. The first one is created with
`python manage.py create_admin <username> "<Full name>"`."""

from datetime import timedelta

from django.db import transaction

from ..conf import get_settings
from ..core import AppError, create_admin_token, endpoint, hash_password, utcnow, verify_password
from ..models import AdminAccount
from ..schemas import AdminCreate, AdminLogin, AdminOut, AdminSession, AdminUpdate, Message, PasswordChange

LOCK_MINUTES = 15
# Checked even when the username doesn't exist, so the response time doesn't reveal valid usernames.
_DUMMY_HASH = hash_password("not-a-real-password")
_BAD_LOGIN = "Wrong username or password."


def _by_username(username: str):
    return AdminAccount.objects.filter(username__iexact=username).first()


@endpoint(body=AdminLogin, limit=("admin-login", 10))
def login(ctx):
    s = get_settings()
    admin = _by_username(ctx.body.username)
    if admin and admin.locked_until and admin.locked_until > utcnow():
        retry = int((admin.locked_until - utcnow()).total_seconds()) + 1
        raise AppError(423, "admin_locked", "Too many wrong passwords. Sign-in is paused for this account.", retry_after=retry)
    ok = verify_password(ctx.body.password, admin.password_hash if admin else _DUMMY_HASH)
    if not admin or not ok:
        if admin:
            admin.failed_logins += 1
            if admin.failed_logins >= s.admin_login_attempts:
                admin.failed_logins = 0
                admin.locked_until = utcnow() + timedelta(minutes=LOCK_MINUTES)
            admin.save(update_fields=["failed_logins", "locked_until", "updated_at"])
        raise AppError(401, "admin_login_failed", _BAD_LOGIN)
    if not admin.is_active:
        raise AppError(403, "account_disabled", "This admin account is disabled.")
    admin.failed_logins, admin.locked_until, admin.last_login_at = 0, None, utcnow()
    admin.save(update_fields=["failed_logins", "locked_until", "last_login_at", "updated_at"])
    token, expires_in = create_admin_token(admin.id, admin.token_version)
    return AdminSession(access_token=token, expires_in=expires_in, admin=AdminOut.model_validate(admin))


@endpoint(auth="admin")
def me(ctx):
    return AdminOut.model_validate(ctx.admin)


@endpoint(auth="admin", body=PasswordChange)
def change_password(ctx):
    admin = ctx.admin
    if not verify_password(ctx.body.current_password, admin.password_hash):
        raise AppError(400, "wrong_password", "Your current password is not correct.")
    admin.password_hash = hash_password(ctx.body.new_password)
    admin.token_version += 1  # signs out every device; the panel asks to sign in again
    admin.save(update_fields=["password_hash", "token_version", "updated_at"])
    return Message(message="Password changed. Please sign in again.")


@endpoint(auth="admin")
def list_accounts(ctx):
    return [AdminOut.model_validate(a) for a in AdminAccount.objects.order_by("created_at")]


@endpoint(auth="admin", body=AdminCreate, status=201)
def create_account(ctx):
    with transaction.atomic():
        if _by_username(ctx.body.username):
            raise AppError(409, "username_taken", "That username is already used by another admin.")
        a = AdminAccount.objects.create(username=ctx.body.username, name=ctx.body.name, password_hash=hash_password(ctx.body.password))
    return AdminOut.model_validate(a)


@endpoint(auth="admin", body=AdminUpdate)
def update_account(ctx, admin_id: str):
    a = AdminAccount.objects.filter(pk=admin_id[:32]).first()
    if not a:
        raise AppError(404, "not_found", "Admin not found.")
    body = ctx.body
    if a.pk == ctx.admin.pk and body.is_active is False:
        raise AppError(400, "cannot_change_self", "You can't disable your own admin account.")
    if body.name is not None:
        a.name = body.name
    if body.is_active is not None and body.is_active != a.is_active:
        a.is_active = body.is_active
        a.token_version += 1
    if body.password is not None:
        a.password_hash = hash_password(body.password)
        a.failed_logins, a.locked_until = 0, None
        a.token_version += 1
    a.save()
    return AdminOut.model_validate(a)
