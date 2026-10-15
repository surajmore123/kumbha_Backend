"""Add the data of another copy of this app's database (e.g. an old server's dump) into this one.

    SOURCE_DATABASE_URL=postgresql://user:pass@host:5432/db python manage.py import_app_db [--dry-run]

Nothing is overwritten: rows whose primary key (or another unique value) already exists are skipped.
Users are matched to existing accounts by id, then mobile number, then email; their rows (chats,
journals, events...) are attached to the matched account. Django's own bookkeeping tables are skipped.
Safe to run more than once.
"""

import os
from collections import defaultdict

import psycopg2
import psycopg2.extras
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

SKIP = {
    "django_migrations", "django_content_type", "django_session", "django_admin_log",
    "auth_permission", "auth_group", "auth_group_permissions",
}  # fmt: skip
# Rows identified by a unique name rather than their id (ids differ between databases).
NEW_ID_TABLES = {"django_celery_beat_periodictask"}
# Columns added after the source was made; filled when the source has no value.
USER_DEFAULTS = {"role": "user", "preferred_language": "en"}


def _phone_key(p: str | None) -> str | None:
    digits = "".join(ch for ch in (p or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else None


class Command(BaseCommand):
    help = "Add another copy of this app's database into this one (no overwrites, users merged)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would happen, then roll back.")

    def handle(self, *args, dry_run=False, **opts):
        url = os.getenv("SOURCE_DATABASE_URL")
        if not url:
            raise CommandError("Set SOURCE_DATABASE_URL to the database to copy from (postgresql://...)")
        src = psycopg2.connect(url)
        src.set_session(readonly=True)
        cur = src.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            with transaction.atomic():
                user_fks = self._user_fk_columns()
                id_map = self._users(cur)
                for table in self._tables_in_order(cur):
                    self._copy(cur, table, user_fks.get(table, []), id_map)
                self._reset_sequences()
                if dry_run:
                    raise _DryRun
        except _DryRun:
            self.stdout.write(self.style.WARNING("Dry run: nothing was saved."))
        finally:
            src.close()

    # ── schema helpers (target database) ──

    def _columns(self, table: str) -> list[str]:
        with connection.cursor() as c:
            c.execute("select column_name from information_schema.columns where table_schema='public' and table_name=%s", [table])
            return [r[0] for r in c.fetchall()]

    def _user_fk_columns(self) -> dict[str, list[str]]:
        with connection.cursor() as c:
            c.execute(
                """select tc.table_name, kcu.column_name
                   from information_schema.table_constraints tc
                   join information_schema.key_column_usage kcu using (constraint_name, table_schema)
                   join information_schema.constraint_column_usage ccu using (constraint_name, table_schema)
                   where tc.constraint_type='FOREIGN KEY' and ccu.table_name='users' and tc.table_schema='public'"""
            )
            out = defaultdict(list)
            for table, col in c.fetchall():
                out[table].append(col)
            return out

    def _tables_in_order(self, cur) -> list[str]:
        """Source tables that also exist here, parents before children (by foreign keys)."""
        cur.execute("select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")
        src_tables = {r["table_name"] for r in cur.fetchall()}
        with connection.cursor() as c:
            c.execute("select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")
            tables = sorted((src_tables & {r[0] for r in c.fetchall()}) - SKIP - {"users"})
            c.execute(
                """select tc.table_name, ccu.table_name from information_schema.table_constraints tc
                   join information_schema.constraint_column_usage ccu using (constraint_name, table_schema)
                   where tc.constraint_type='FOREIGN KEY' and tc.table_schema='public'"""
            )
            parents = defaultdict(set)
            for child, parent in c.fetchall():
                if child != parent:
                    parents[child].add(parent)
        ordered, done = [], {"users"} | SKIP
        while len(ordered) < len(tables):
            ready = [t for t in tables if t not in done and parents[t] <= done | (set(parents[t]) - set(tables))]
            if not ready:
                raise CommandError(f"Circular foreign keys between: {sorted(set(tables) - done)}")
            for t in ready:
                ordered.append(t)
                done.add(t)
        return ordered

    # ── users ──

    def _users(self, cur) -> dict:
        target_cols = self._columns("users")
        with connection.cursor() as c:
            c.execute("select user_id, phone_number, lower(email) from users")
            existing = c.fetchall()
        by_id = {row[0] for row in existing}
        by_phone = {_phone_key(p): uid for uid, p, _ in existing if _phone_key(p)}
        by_email = {e: uid for uid, _, e in existing if e}

        cur.execute("select * from users")
        id_map, created, matched = {}, 0, 0
        for u in cur.fetchall():
            uid = u["user_id"]
            match = uid if uid in by_id else by_phone.get(_phone_key(u.get("phone_number"))) or by_email.get((u.get("email") or "").lower() or None)
            if match:
                id_map[uid] = match
                matched += 1
                continue
            row = {c: u[c] for c in target_cols if c in u}
            for col, default in USER_DEFAULTS.items():
                if col in target_cols and row.get(col) is None:
                    row[col] = default
            self._insert("users", row)
            id_map[uid] = uid
            by_id.add(uid)
            if _phone_key(u.get("phone_number")):
                by_phone[_phone_key(u["phone_number"])] = uid
            if u.get("email"):
                by_email[u["email"].lower()] = uid
            created += 1
        self.stdout.write(f"users: {created} added, {matched} matched to existing accounts")
        return id_map

    # ── everything else ──

    def _insert(self, table: str, row: dict) -> int:
        cols = list(row)
        quoted = ", ".join(f'"{c}"' for c in cols)
        sql = f'INSERT INTO "{table}" ({quoted}) VALUES ({", ".join(["%s"] * len(cols))}) ON CONFLICT DO NOTHING'
        values = [psycopg2.extras.Json(v) if isinstance(v, (dict, list)) else v for v in row.values()]
        with connection.cursor() as c:
            c.execute(sql, values)
            return c.rowcount

    def _copy(self, cur, table: str, user_cols: list[str], id_map: dict) -> None:
        target_cols = set(self._columns(table))
        cur.execute(f'select * from "{table}"')
        rows = cur.fetchall()
        added = 0
        for r in rows:
            row = {c: v for c, v in r.items() if c in target_cols}
            if table in NEW_ID_TABLES:
                row.pop("id", None)  # matched on its unique name; take a fresh id
            for col in user_cols:
                if row.get(col) is not None:
                    row[col] = id_map.get(row[col], row[col])
            added += self._insert(table, row)
        if rows:
            self.stdout.write(f"{table}: {added} added, {len(rows) - added} already there")

    def _reset_sequences(self) -> None:
        """Rows were inserted with their ids, so move each id counter past the highest id."""
        with connection.cursor() as c:
            c.execute(
                """select table_name, column_name, pg_get_serial_sequence(quote_ident(table_name), column_name)
                   from information_schema.columns where table_schema='public'
                   and pg_get_serial_sequence(quote_ident(table_name), column_name) is not null"""
            )
            for table, col, seq in c.fetchall():
                c.execute(f'select setval(%s, coalesce((select max("{col}") from "{table}"), 0) + 1, false)', [seq])


class _DryRun(Exception):
    pass
