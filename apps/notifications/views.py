"""
The notification centre (all under /api/notifications/, JWT required). Everyone
reaches only their own rows, and another person's id gets 404.
"""

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status

from apps.crowd.models.AppNotification import AppNotification
from apps.family.views import _Family, error, ok
from apps.notifications.models import Notification, NotificationState

PAGE_SIZE = 30
GENERAL = Notification.Category.GENERAL


def _body(row):
    delivery = getattr(row, "delivery", None)
    return {
        "id": str(row.pk),
        "category": row.category,
        "title": row.title,
        "body": row.body,
        "data": row.data,
        "read": row.read_at is not None,
        "created_at": row.created_at,
        "delivery": delivery.state if delivery else None,
    }


def _general_rows():
    return AppNotification.objects.filter(is_active=True, del_flag=0).order_by("-created_at")


def _read_up_to(user):
    state = NotificationState.objects.filter(user=user).first()
    return state.general_read_at if state else None


def _general_unread(user):
    seen = _read_up_to(user)
    return _general_rows().filter(created_at__gt=seen).count() if seen else _general_rows().count()


def _mark_general(user):
    NotificationState.objects.update_or_create(user=user, defaults={"general_read_at": timezone.now()})


class NotificationListAPI(_Family):
    def get(self, request):
        category = request.query_params.get("category")
        if category and category not in Notification.Category.values:
            return error({"category": ["Unknown category."]})
        if category == GENERAL:
            return self.general(request)
        rows = Notification.objects.filter(user=request.user).select_related("delivery")
        if category:
            rows = rows.filter(category=category)
        if request.query_params.get("unread") == "true":
            rows = rows.filter(read_at__isnull=True)
        page = Paginator(rows, PAGE_SIZE).get_page(request.query_params.get("page"))
        # This phone has it now, which is all "delivered" can honestly mean.
        fresh = [row.pk for row in page if row.delivered_at is None]
        if fresh:
            Notification.objects.filter(pk__in=fresh).update(delivered_at=timezone.now())
        return ok({"results": [_body(r) for r in page], "count": page.paginator.count, "has_next": page.has_next()})

    def general(self, request):
        seen = _read_up_to(request.user)
        page = Paginator(_general_rows(), PAGE_SIZE).get_page(request.query_params.get("page"))
        return ok({
            "results": [{
                "id": f"general:{row.pk}", "category": GENERAL, "title": row.title, "body": row.body,
                "data": {"route": "/notifications"}, "read": seen is not None and row.created_at <= seen,
                "created_at": row.created_at, "delivery": None,
            } for row in page],
            "count": page.paginator.count,
            "has_next": page.has_next(),
        })


class NotificationSummaryAPI(_Family):
    def get(self, request):
        rows = Notification.objects.filter(user=request.user, read_at__isnull=True)
        by_category = {c: rows.filter(category=c).count() for c in Notification.Category.values if c != GENERAL}
        by_category[GENERAL] = _general_unread(request.user)
        return ok({"unread": sum(by_category.values()), "by_category": by_category})


class NotificationReadAPI(_Family):
    def post(self, request, notification_id):
        row = get_object_or_404(Notification, pk=notification_id, user=request.user)
        if row.read_at is None:
            row.read_at = timezone.now()
            row.save(update_fields=["read_at"])
        return ok({"read": True})


class NotificationReadAllAPI(_Family):
    def post(self, request):
        category = request.data.get("category")
        if category and category not in Notification.Category.values:
            return error({"category": ["Unknown category."]}, status.HTTP_400_BAD_REQUEST)
        if category != GENERAL:
            rows = Notification.objects.filter(user=request.user, read_at__isnull=True)
            if category:
                rows = rows.filter(category=category)
            rows.update(read_at=timezone.now())
        if not category or category == GENERAL:
            _mark_general(request.user)
        return ok({"read": True})
