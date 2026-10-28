"""
Read-only crowd and incident tools for Guru AI.

Crowd measurements come from `ZoneCrowdSnapshot` rows written by the crowd
engine (`apps.crowd.services.crowd_engine.generate_snapshots`). Every
result carries the snapshot's `calculated_at` and a `stale` flag, because
the data is only as current as the last engine run. `Temple.crowd_level`
is a separate admin advisory and is never reported as a measurement here.
"""

import re

from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone

from apps.aiChat import ai_config
from apps.aiChat.services.geo import distance_km, valid_coordinates
from apps.crowd.models import Incident, Zone, ZoneCrowdSnapshot

# Zones within this distance of a temple are reported for it when the
# zone has no radius of its own.
_DEFAULT_ZONE_RADIUS_M = 1000

_NORMALIZE = re.compile(r"[^a-z0-9ऀ-ॿ]+")


def _active_zones():
    return Zone.objects.filter(is_active=True, del_flag=0)


def _zone_snapshot(zone: Zone, snapshot: ZoneCrowdSnapshot | None, now) -> dict:
    result = {
        "zone_id": str(zone.id),
        "code": zone.code,
        "name": zone.name,
        "city": zone.city,
        "status": None,
        "occupancy_percent": None,
        "total_people": None,
        "incident_count": None,
        "calculated_at": None,
        "age_minutes": None,
        "stale": True,
        "source": "zone_crowd_snapshot",
    }
    if snapshot is None:
        return result
    age = max(0, int((now - snapshot.calculated_at).total_seconds() // 60))
    result.update(
        status=snapshot.status,
        occupancy_percent=round(snapshot.occupancy_percent, 1),
        total_people=snapshot.total_people,
        incident_count=snapshot.incident_count,
        calculated_at=snapshot.calculated_at.isoformat(),
        age_minutes=age,
        stale=age > ai_config.crowd_stale_minutes(),
    )
    return result


def get_zone_crowd(zone_ids: list | None = None, limit: int = 10) -> list[dict]:
    """Latest snapshot per active zone (or per given zone)."""
    latest = (
        ZoneCrowdSnapshot.objects.filter(zone=OuterRef("pk"), del_flag=0)
        .order_by("-calculated_at")
        .values("pk")[:1]
    )
    zones = _active_zones().annotate(latest_snapshot_id=Subquery(latest))
    if zone_ids is not None:
        zones = zones.filter(id__in=zone_ids)
    zones = list(zones.order_by("-priority", "name")[:limit])

    snapshots = ZoneCrowdSnapshot.objects.in_bulk(
        [z.latest_snapshot_id for z in zones if z.latest_snapshot_id]
    )
    now = timezone.now()
    return [
        _zone_snapshot(zone, snapshots.get(zone.latest_snapshot_id), now)
        for zone in zones
    ]


def find_zones_in_question(question: str) -> list[str]:
    """Ids of zones whose name or code is mentioned in the question."""
    normalized = f" {_NORMALIZE.sub(' ', (question or '').lower())} "
    found = []
    for zone in _active_zones().only("id", "name", "code"):
        name = _NORMALIZE.sub(" ", zone.name.lower()).strip()
        words = [w for w in name.split() if len(w) >= 5 and w != "temple"]
        code = _NORMALIZE.sub(" ", zone.code.lower()).strip()
        if (
            f" {name} " in normalized
            or f" {code} " in normalized
            or any(f" {w} " in normalized for w in words)
        ):
            found.append(zone.id)
    return found


def zones_near(latitude, longitude) -> list[str]:
    """Ids of zones covering (or close to) a point, nearest first."""
    if not valid_coordinates(latitude, longitude):
        return []
    hits = []
    for zone in _active_zones().only("id", "latitude", "longitude", "radius_m"):
        if not valid_coordinates(zone.latitude, zone.longitude):
            continue
        meters = distance_km(latitude, longitude, zone.latitude, zone.longitude) * 1000
        if meters <= max(zone.radius_m or 0, _DEFAULT_ZONE_RADIUS_M):
            hits.append((meters, zone.id))
    return [zone_id for _, zone_id in sorted(hits)]


def get_active_incidents(
    zone_ids: list | None = None,
    types: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Incidents that are active now, most severe and recent first."""
    now = timezone.now()
    incidents = Incident.objects.filter(
        is_active=True,
        del_flag=0,
        start_time__lte=now,
        zone__is_active=True,
        zone__del_flag=0,
    ).filter(Q(end_time__isnull=True) | Q(end_time__gt=now))
    if zone_ids is not None:
        incidents = incidents.filter(zone_id__in=zone_ids)
    if types:
        incidents = incidents.filter(incident_type__in=types)

    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    rows = sorted(
        incidents.select_related("zone")[:100],
        key=lambda i: (severity_rank.get(i.severity, 9), -i.start_time.timestamp()),
    )[:limit]
    return [
        {
            "id": str(incident.id),
            "zone": incident.zone.name,
            "type": incident.incident_type,
            "severity": incident.severity,
            "title": incident.title,
            "description": incident.description,
            "start_time": incident.start_time.isoformat(),
            "end_time": incident.end_time.isoformat() if incident.end_time else None,
            "updated_at": incident.updated_at.isoformat() if incident.updated_at else None,
        }
        for incident in rows
    ]


def freshness(zones: list[dict]) -> dict | None:
    """Most recent snapshot among the zones, for the answer footer."""
    times = [z for z in zones if z.get("calculated_at")]
    if not times:
        return None
    newest = min(times, key=lambda z: z["age_minutes"])
    return {
        "calculated_at": newest["calculated_at"],
        "age_minutes": newest["age_minutes"],
        "stale": newest["stale"],
    }
