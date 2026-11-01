"""
Health checks. `health/` and `health/ready/` are public for load balancers, so
they say only whether each part works. Counts are for administrators.
"""

from datetime import timedelta
import logging

from django.db import connection
from django.utils import timezone
from django_celery_beat.models import PeriodicTask
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import status

from apps.celery import app as celery_app
from apps.emergency.models import ACTIVE_STATUSES as ACTIVE_SOS
from apps.emergency.models import EmergencySOS
from apps.family.views import ok
from apps.familylocation.models import LocationSession
from apps.lostfound.models import ACTIVE_STATUSES, LostFoundCase
from apps.notifications.models import NotificationDelivery

logger = logging.getLogger("kumbha.health")

# A sweep that hasn't run for this long has stopped: expiry and escalation are late.
STALE_AFTER = timedelta(minutes=15)
SWEEPS = ("Sweep emergency SOS", "Sweep family location sharing")


def _database():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return True


def _broker():
    with celery_app.connection_for_read() as connection_:
        connection_.ensure_connection(max_retries=1, timeout=2)
    return True


def _sweeps():
    tasks = list(PeriodicTask.objects.filter(name__in=SWEEPS, enabled=True))
    cutoff = timezone.now() - STALE_AFTER
    return len(tasks) == len(SWEEPS) and all(t.last_run_at and t.last_run_at > cutoff for t in tasks)


def _check(check):
    try:
        return check()
    except Exception as failure:
        logger.error("Health check failed", extra={"error_type": type(failure).__name__, "event": "health"})
        return False


class LiveAPI(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return ok({"alive": True})


class ReadyAPI(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        checks = {"database": _check(_database), "broker": _check(_broker)}
        background = _check(_sweeps) if checks["database"] else False
        # Late sweeps need attention, but restarting the web tier won't fix them.
        ready = all(checks.values())
        return ok(
            {"ready": ready, **checks, "background_tasks": background},
            status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class OperationsHealthAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        hour_ago = timezone.now() - timedelta(hours=1)
        deliveries = NotificationDelivery.objects.filter(created_at__gte=hour_ago)
        sweeps = PeriodicTask.objects.filter(name__in=SWEEPS).values("name", "enabled", "last_run_at")
        return ok({
            "database": _check(_database),
            "broker": _check(_broker),
            "sweeps": list(sweeps),
            "notifications_last_hour": {
                state: deliveries.filter(state=state).count()
                for state in NotificationDelivery.State.values
            },
            "open_cases": LostFoundCase.objects.filter(status__in=ACTIVE_STATUSES).count(),
            "open_sos": EmergencySOS.objects.filter(status__in=ACTIVE_SOS).count(),
            "active_location_sessions": LocationSession.objects.filter(status="active").count(),
        })
