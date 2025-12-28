import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )

    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))



def log_temple_event(
    *,
    request,
    temple,
    event_type,
    user_lat=None,
    user_lng=None,
):
    from .models import TempleAnalyticsView

    TempleAnalyticsView.objects.create(
        user=request.user if request.user.is_authenticated else None,
        temple=temple,
        event_type=event_type,
        user_latitude=user_lat,
        user_longitude=user_lng,
    )

