from django.db.models import Count
from django.utils import timezone
from apps.crowd.models import AppNotification, Zone

from apps.crowd.models import UserZonePresence
from apps.crowd.models.ZoneCrowdShanp import ZoneCrowdSnapshot
from utils.push_notifications import send_push_to_all 
from datetime import timedelta


def get_live_count():

    data = (
        UserZonePresence.objects.filter(is_active=True, del_flag=0).values("zone").annotate(total=Count("id"))


    )

    result = {}

    for item in data:
        result[item["zone"]] = item["total"]

    return result


def get_status_from_percent(percent):
    if percent <= 40:
        return ZoneCrowdSnapshot.LOW
    elif percent <= 70:
        return ZoneCrowdSnapshot.MEDIUM
    elif percent <= 100:
        return ZoneCrowdSnapshot.HIGH
    else:
        return ZoneCrowdSnapshot.CRITICAL

def generate_snapshots():
    """
    Creates crowd snapshot for all zones.
    """

    now = timezone.now()

    # ------------------------------------
    # AUTO DEACTIVATE INACTIVE USERS
    # ------------------------------------
    cleanup_inactive_users()

    # ------------------------------------
    # AFTER CLEANUP → calculate live counts
    # ------------------------------------
    live_counts = get_live_count()

    zones = Zone.objects.filter(is_active=True, del_flag=0)

    for zone in zones:
        people = live_counts.get(zone.id, 0)

        if zone.capacity > 0:
            percent = (people / zone.capacity) * 100
        else:
            percent = 0

        status = get_status_from_percent(percent)

        previous = (
            ZoneCrowdSnapshot.objects
            .filter(zone=zone)
            .order_by("-calculated_at")
            .first()
        )

        print(
            "ZONE:", zone.name,
            "PREVIOUS:", previous.status if previous else None,
            "NEW:", status
        )

        if previous and severity_rank(status) > severity_rank(previous.status):
            title = f"Crowd Alert: {zone.name}"
            body = f"Status changed to {status}. Please be careful."
            send_push_to_all(
                title, body,
                data={"type": "crowd_alert", "zone_id": zone.id, "route": "/liveCroud"},
                category="crowd_alerts",
            )

        ZoneCrowdSnapshot.objects.create(
            zone=zone,
            total_people=people,
            occupancy_percent=percent,
            status=status,
            calculated_at=now
        )



def severity_rank(status):
    order = {
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
        "CRITICAL": 4,
        "CLOSED": 5,
    }
    return order.get(status, 0)


def generate_zone_snapshot(zone):
    """
    Recalculate crowd status for a single zone.
    Trigger push + save notification if status changes.
    """

    cleanup_inactive_users()

    now = timezone.now()

    live_counts = get_live_count()
    people = live_counts.get(zone.id, 0)

    # calculate occupancy %
    if zone.capacity > 0:
        percent = (people / zone.capacity) * 100
    else:
        percent = 0

    new_status = get_status_from_percent(percent)

    previous_snapshot = (
        ZoneCrowdSnapshot.objects
        .filter(zone=zone)
        .order_by("-calculated_at")
        .first()
    )

    previous_status = previous_snapshot.status if previous_snapshot else None

    print(f"ZONE: {zone.name} PREVIOUS: {previous_status} NEW: {new_status}")

    # Always save snapshot
    ZoneCrowdSnapshot.objects.create(
        zone=zone,
        total_people=people,
        occupancy_percent=percent,
        status=new_status,
        calculated_at=now
    )

    # 🔥 ONLY IF STATUS CHANGED → Push + Save Notification
    if previous_status and previous_status != new_status:

        title = f"Crowd Update: {zone.name}"
        body = f"Status changed to {new_status}. Please be careful."

        # 1️⃣ Save in notification feed
        AppNotification.objects.create(
            title=title,
            body=body,
            type="ALERT",
            zone=zone,
            severity=new_status
        )

        # 2️⃣ Send push
        send_push_to_all(
            title, body,
            data={"type": "crowd_alert", "zone_id": zone.id, "route": "/liveCroud"},
            category="crowd_alerts",
        )

def cleanup_inactive_users():
    """
    Marks users inactive if they haven't updated location for 3 minutes.
    """

    now = timezone.now()
    inactive_threshold = now - timedelta(minutes=3)

    inactive_presences = UserZonePresence.objects.filter(
        is_active=True,
        last_seen_at__lt=inactive_threshold,
        del_flag=0
    )

    for presence in inactive_presences:
        presence.is_active = False
        presence.exited_at = now
        presence.save(update_fields=["is_active", "exited_at"])
