"""Which operational zone a position falls in. Works from the existing Zone table."""

from apps.aiChat.services.geo import distance_km, valid_coordinates
from apps.crowd.models.Zone import Zone


def zone_for(latitude, longitude):
    """The nearest active zone whose radius holds this point, or None. A zone
    with no radius can't be matched, rather than guessing."""
    if latitude is None or longitude is None or not valid_coordinates(latitude, longitude):
        return None
    best, best_km = None, None
    for zone in Zone.objects.filter(is_active=True, del_flag=0, radius_m__isnull=False):
        km = distance_km(latitude, longitude, zone.latitude, zone.longitude)
        if km * 1000 <= zone.radius_m and (best is None or km < best_km):
            best, best_km = zone, km
    return best
