"""
Reproducible load scenarios on synthetic data.

    python scripts/load_test.py seed
    python scripts/load_test.py run --base-url http://127.0.0.1:8018 --concurrency 5 20 50
    python scripts/load_test.py cleanup

It refuses any host that isn't this machine, so it can't be pointed at production.
Everything it makes uses the +91 92 999 phone range and the LOADTEST zone, which is
how `cleanup` finds them. Throttles are real, so scenarios that would hit a limit
spread requests across synthetic users rather than disabling it.
"""

import argparse
import json
import os
import platform
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

PREFIX = "+9192999"
USERS = 300
CASES = 2000
NOTIFICATIONS = 5000
SOS_PER_LEVEL = 90
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
TOKENS = ROOT / "load_tokens.json"


def setup():
    import django

    django.setup()


def phone(index):
    return f"{PREFIX}{index:05d}"


def seed():
    setup()
    from django.utils import timezone
    from rest_framework_simplejwt.tokens import RefreshToken

    from apps.authentication.models import User
    from apps.crowd.models.Zone import Zone
    from apps.family.models import FamilyCircle, FamilyMember
    from apps.lostfound.models import LostFoundCase
    from apps.notifications.models import Notification
    from apps.safety.models import SafetyHelper

    zone, _ = Zone.objects.get_or_create(
        code="LOADTEST",
        defaults={"name": "Load Test", "city": "Test", "latitude": "19.9975", "longitude": "73.7898", "radius_m": 1000},
    )
    User.objects.bulk_create(
        [User(phone_number=phone(i), full_Name="Load Test", is_active=True) for i in range(USERS)],
        ignore_conflicts=True,
    )
    users = list(User.objects.filter(phone_number__startswith=PREFIX).order_by("phone_number"))
    staff, volunteer = users[0], users[1]
    SafetyHelper.objects.update_or_create(user=staff, defaults={"role": "safety_staff"})[0].zones.add(zone)
    SafetyHelper.objects.update_or_create(user=volunteer, defaults={"role": "volunteer"})[0].zones.add(zone)

    now = timezone.now()
    LostFoundCase.objects.bulk_create([
        LostFoundCase(
            case_type="lost" if i % 2 else "found", reporter=users[2 + i % (USERS - 2)], event_at=now,
            location_text="LOADTEST ghat", clothing_description="Synthetic blue shirt", zone=zone,
            assigned_to=volunteer if i % 20 == 0 else None,
        )
        for i in range(CASES)
    ], batch_size=500)
    Notification.objects.bulk_create([
        Notification(
            user=users[2 + i % 50], category="general", dedupe_key=f"loadtest:{i}", title="Load test", body="Synthetic",
        )
        for i in range(NOTIFICATIONS)
    ], batch_size=1000)

    family_ids = {}
    for user in users[2:102]:
        family = FamilyCircle.objects.create(name="Load Test")
        FamilyMember.objects.create(
            family=family, user=user, kind="account_holder", role="organizer", relationship="self", full_name="Load Test",
        )
        family_ids[str(user.pk)] = str(family.pk)

    tokens = [str(RefreshToken.for_user(user).access_token) for user in users]
    TOKENS.write_text(json.dumps({"tokens": tokens}))
    print(f"seeded {len(users)} users, {CASES} cases, {NOTIFICATIONS} notifications, {len(family_ids)} families")


def cleanup():
    setup()
    from apps.authentication.models import Otp, User
    from apps.crowd.models.Zone import Zone
    from apps.emergency.models import EmergencySOS
    from apps.family.models import FamilyCircle
    from apps.lostfound.models import LostFoundCase
    from apps.notifications.models import Notification
    from apps.safety.models import SafetyHelper

    users = User.objects.filter(phone_number__startswith=PREFIX)
    Notification.objects.filter(user__in=users).delete()
    EmergencySOS.objects.filter(user__in=users).delete()
    LostFoundCase.objects.filter(reporter__in=users).delete()
    FamilyCircle.objects.filter(members__user__in=users).distinct().delete()
    SafetyHelper.objects.filter(user__in=users).delete()
    Otp.objects.filter(user__in=users).delete()
    users.delete()
    Zone.objects.filter(code="LOADTEST").delete()
    TOKENS.unlink(missing_ok=True)
    print("removed; synthetic users left:", User.objects.filter(phone_number__startswith=PREFIX).count())


class Runner:
    def __init__(self, base_url):
        self.base = base_url.rstrip("/") + "/api/"
        self.tokens = json.loads(TOKENS.read_text())["tokens"]
        self.staff, self.volunteer, self.pilgrims = self.tokens[0], self.tokens[1], self.tokens[2:]
        self.sos_used = 0

    def call(self, method, path, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response.read()
                code = response.status
        except urllib.error.HTTPError as failure:
            failure.read()
            code = failure.code
        except OSError:
            code = 0
        return (time.perf_counter() - started) * 1000, code

    def pilgrim(self, index):
        return self.pilgrims[index % len(self.pilgrims)]

    def scenarios(self, run_id):
        return {
            "auth: request OTP": (lambda i: self.call("POST", "auth/send-mobile-otp/", {"phone_number": f"92999{50000 + run_id * 100 + i}"}), 201),
            "profile read": (lambda i: self.call("GET", "auth/profile/", token=self.pilgrim(i)), 200),
            "family: list circles": (lambda i: self.call("GET", "family/circles/", token=self.pilgrim(i)), 200),
            "lost & found: report": (lambda i: self.call("POST", "lostfound/cases/", {
                "client_id": str(uuid.uuid4()), "relationship": "Parent", "location_text": "LOADTEST ghat",
                "clothing_description": "Synthetic red kurta", "event_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }, self.pilgrim(i)), 201),
            "lost & found: staff list": (lambda i: self.call("GET", "lostfound/ops/cases/", token=self.staff), 200),
            # One open SOS per person, so each request needs a different person.
            "sos: create": (lambda i: self.call("POST", "emergency/sos/", {
                "client_id": str(uuid.uuid4()), "category": "medical",
            }, self.pilgrims[-1 - (i + self.sos_used)]), 201, SOS_PER_LEVEL),
            "notifications: list": (lambda i: self.call("GET", "notifications/", token=self.pilgrims[i % 50]), 200),
            "volunteer: my cases": (lambda i: self.call("GET", "operations/cases/", token=self.volunteer), 200),
        }

    def run(self, concurrency, requests):
        rows = []
        for name, (action, expected, *limit) in self.scenarios(concurrency).items():
            count = min(requests, *limit) if limit else requests
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                results = list(pool.map(action, range(count)))
            elapsed = time.perf_counter() - started
            times = sorted(result[0] for result in results)
            codes = {}
            for _, code in results:
                codes[code] = codes.get(code, 0) + 1
            failed = sum(number for code, number in codes.items() if code != expected)
            rows.append({
                "scenario": name, "concurrency": concurrency, "requests": count,
                "throughput_rps": round(count / elapsed, 1), "p50_ms": round(statistics.median(times)),
                "p95_ms": round(times[int(len(times) * 0.95) - 1]), "max_ms": round(times[-1]),
                "error_rate_pct": round(failed / count * 100, 1), "statuses": codes,
            })
            print(json.dumps(rows[-1]))
        self.sos_used += SOS_PER_LEVEL
        return rows


def run(args):
    host = urllib.parse.urlparse(args.base_url).hostname
    if host not in LOCAL_HOSTS:
        sys.exit(f"Refusing to load test {host}: this tool only runs against this machine.")
    runner = Runner(args.base_url)
    rows = [row for level in args.concurrency for row in runner.run(level, args.requests)]
    report = {
        "machine": f"{platform.system()} {platform.release()}, {os.cpu_count()} logical CPUs",
        "server": args.server, "results": rows,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print("wrote", args.out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "run", "cleanup"])
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    parser.add_argument("--concurrency", type=int, nargs="+", default=[5, 20, 50])
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--server", default="not stated")
    parser.add_argument("--out", default="load_report.json")
    options = parser.parse_args()
    {"seed": seed, "cleanup": cleanup}.get(options.command, lambda: run(options))()
