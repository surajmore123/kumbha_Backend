import math
from apps.crowd.models import Zone


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Returns distance in meters
    """
    R = 6371000  # Earth radius in meters

    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))

    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(delta_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2) ** 2

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def find_zone(latitude, longitude):
    """
    Returns zone object if user is inside any zone.
    """

    zones = Zone.objects.filter(
        is_active=True,
        del_flag=0,
        radius_m__isnull=False
    )

    for zone in zones:
        distance = haversine_distance(
            latitude,
            longitude,
            zone.latitude,
            zone.longitude
        )

        if distance <= zone.radius_m:
            return zone

    return None