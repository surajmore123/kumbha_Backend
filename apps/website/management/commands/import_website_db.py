"""Copy the old FastAPI website database into this one (safe to run more than once).

    OLD_DATABASE_URL=postgresql://user:pass@host:5432/db python manage.py import_website_db [--dry-run]

Users are merged into the shared accounts: an old website user is matched to an existing user by email,
then by mobile number (+91XXXXXXXXXX), else created with the same id, so website tokens keep working.
Rows that already exist (same id) are skipped.
"""

import os
import uuid

import psycopg2
import psycopg2.extras
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.authentication.models import User

ROLE_RANK = {"user": 0, "partner": 1, "admin": 2}

# old table -> (new table, columns copied as-is, user-id columns to remap {old column: new column})
TABLES = [
    ("partners", "website_partner",
     ["id", "created_at", "updated_at", "name", "category", "contact_phone", "contact_email", "town", "registration_number", "status", "notes"],
     {"owner_user_id": "owner_user_id"}),
    ("listings", "website_listing",
     ["id", "created_at", "updated_at", "partner_id", "category", "name", "type", "town", "area", "price_from", "unit", "highlights",
      "distance", "duration", "trust", "wheelchair", "image", "status", "is_sample", "source", "external_id"],
     {}),
    ("enquiries", "website_enquiry",
     ["id", "created_at", "updated_at", "listing_id", "subject", "name", "phone", "date_from", "date_to", "people", "notes", "language", "status", "ip_hash"],
     {"user_id": "user_id"}),
    ("waitlist", "website_waitlistentry", ["id", "created_at", "updated_at", "name", "contact", "language"], {}),
    ("safety_cards", "website_safetycard",
     ["id", "created_at", "updated_at", "title", "name", "age", "blood", "phones", "meet", "notes", "photo"],
     {"user_id": "user_id"}),
    ("user_items", "website_useritem", ["id", "created_at", "updated_at", "kind", "key", "data"], {"user_id": "user_id"}),
    ("announcements", "website_announcement",
     ["id", "created_at", "updated_at", "title", "body", "link", "kind", "pinned", "published", "starts_on", "ends_on"],
     {"created_by": "created_by_id"}),
    ("refresh_tokens", "website_refreshtoken",
     ["id", "created_at", "updated_at", "token_hash", "expires_at", "revoked_at", "user_agent"],
     {"user_id": "user_id"}),
    ("phone_locks", "website_phonelock", ["phone", "locked_until", "created_at", "updated_at"], {}),
]


def _phone_variants(phone10: str) -> list[str]:
    return [f"+91{phone10}", phone10, f"91{phone10}"]


class Command(BaseCommand):
    help = "Copy the old website (FastAPI) database into the Django database, merging users."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would happen, then roll back.")

    def handle(self, *args, dry_run=False, **opts):
        url = os.getenv("OLD_DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
        if not url:
            raise CommandError("Set OLD_DATABASE_URL to the old website database (postgresql://...)")
        old = psycopg2.connect(url)
        old.set_session(readonly=True)
        cur = old.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            with transaction.atomic():
                id_map = self._users(cur)
                for old_table, new_table, cols, user_cols in TABLES:
                    self._copy(cur, old_table, new_table, cols, user_cols, id_map)
                if dry_run:
                    raise _DryRun
        except _DryRun:
            self.stdout.write(self.style.WARNING("Dry run: nothing was saved."))
        finally:
            old.close()

    def _users(self, cur) -> dict[str, uuid.UUID]:
        cur.execute("SELECT * FROM users ORDER BY created_at")
        id_map, created, merged = {}, 0, 0
        for u in cur.fetchall():
            uid = uuid.UUID(hex=u["id"])
            user = User.objects.filter(user_id=uid).first()
            if user is None and u["email"]:
                user = User.objects.filter(email__iexact=u["email"]).first()
            if user is None and u["phone"]:
                user = User.objects.filter(phone_number__in=_phone_variants(u["phone"])).first()
            if user is None:
                user = User(
                    user_id=uid,
                    phone_number=f"+91{u['phone']}" if u["phone"] else None,
                    email=u["email"],
                    full_Name=u["name"],
                    role=u["role"],
                    is_active=u["is_active"],
                    preferred_language=u["preferred_language"] or "en",
                    last_login=u["last_login_at"],
                    otp_verified=bool(u["phone"]),
                )
                user.save()
                User.objects.filter(pk=user.pk).update(created_at=u["created_at"])
                created += 1
            else:
                if ROLE_RANK.get(u["role"], 0) > ROLE_RANK.get(user.role, 0):
                    user.role = u["role"]
                if user.preferred_language == "en" and u["preferred_language"]:
                    user.preferred_language = u["preferred_language"]
                user.full_Name = user.full_Name or u["name"]
                user.email = user.email or u["email"]
                if u["phone"] and not user.phone_number:
                    user.phone_number = f"+91{u['phone']}"
                if u["last_login_at"] and (not user.last_login or u["last_login_at"] > user.last_login):
                    user.last_login = u["last_login_at"]
                user.save()
                merged += 1
            id_map[u["id"]] = user.pk
        self.stdout.write(f"users: {created} created, {merged} matched to existing accounts")
        return id_map

    def _copy(self, cur, old_table, new_table, cols, user_cols, id_map):
        cur.execute(f"SELECT * FROM {old_table}")  # noqa: S608 - table names are constants above
        rows = cur.fetchall()
        out_cols = cols + list(user_cols.values())
        placeholders = ", ".join(["%s"] * len(out_cols))
        sql = f'INSERT INTO {new_table} ({", ".join(out_cols)}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
        inserted = 0
        with connection.cursor() as dst:
            for r in rows:
                values = [psycopg2.extras.Json(r[c]) if c == "highlights" else r[c] for c in cols]
                values += [id_map.get(r[old_col]) if r[old_col] else None for old_col in user_cols]
                dst.execute(sql, values)
                inserted += dst.rowcount
        self.stdout.write(f"{old_table}: {inserted} copied, {len(rows) - inserted} already there")


class _DryRun(Exception):
    pass
