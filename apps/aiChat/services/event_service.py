
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.aiChat.services.geo import map_links
from apps.events.models.EventModel import Event


def _visible_events():
    """
    Events the app shows to pilgrims: published, verified, visible and not
    soft-deleted or expired. `is_verified` is the application's review
    status, not independent proof that an authority confirmed the event.
    """
    today = timezone.localdate()
    return Event.objects.filter(
        status="PUBLISHED",
        is_verified=True,
        show_in_app=True,
        del_flag=0,
    ).exclude(
        Q(auto_expire=True) & Q(expiry_date__lt=today)
    )


def _event_dict(event: Event) -> dict:
    latitude = float(event.latitude) if event.latitude is not None else None
    longitude = float(event.longitude) if event.longitude is not None else None
    return {
        "id": str(event.event_id),
        "name": event.event_name,
        "description": event.short_description or event.description or "",
        "category": event.event_category,
        "subtype": event.event_subtype,
        "date": event.event_date.isoformat(),
        "start_time": event.start_time.isoformat() if event.start_time else None,
        "end_time": event.end_time.isoformat() if event.end_time else None,
        "is_all_day": event.is_all_day,
        "location": event.location_name or event.location_type,
        "expected_crowd_level": event.expected_crowd_level,
        "is_crowd_sensitive": event.is_crowd_sensitive,
        "requires_police_advisory": event.requires_police_advisory,
        "data_source": event.data_source,
        "is_verified": event.is_verified,
        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
        **map_links(latitude, longitude),
    }


def get_upcoming_verified_events(
    limit: int = 10,
    category: str | None = None,
) -> list[dict]:
    """Return upcoming published and verified events visible in the app."""

    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50.")

    events = _visible_events().filter(event_date__gte=timezone.localdate())
    if category:
        events = events.filter(event_category=category)
    events = events.order_by("event_date", "start_time")[:limit]
    return [_event_dict(event) for event in events]


def get_recently_updated_events(days: int = 14, limit: int = 10) -> list[dict]:
    """Visible upcoming events whose record changed in the last `days`."""
    since = timezone.now() - timedelta(days=days)
    events = (
        _visible_events()
        .filter(event_date__gte=timezone.localdate(), updated_at__gte=since)
        .order_by("-updated_at")[:limit]
    )
    return [_event_dict(event) for event in events]


def get_events_by_ids(ids: list[str]) -> list[dict]:
    """Re-read events referenced earlier in the conversation."""
    clean = [str(i) for i in ids if i][:10]
    if not clean:
        return []
    try:
        events = list(_visible_events().filter(event_id__in=clean))
    except Exception:  # noqa: BLE001 - malformed UUIDs from old metadata
        return []
    order = {value: index for index, value in enumerate(clean)}
    events.sort(key=lambda e: order.get(str(e.event_id), 99))
    return [_event_dict(event) for event in events]
