import logging
import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

logger = logging.getLogger(__name__)

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



def _coordinate(value, limit):
    """
    A latitude/longitude from a request as a Decimal with 6 places, or None
    when it's missing, empty ("lat=" is sent when the app has no location),
    not a number or out of range.
    """
    if value is None or str(value).strip() == "":
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or abs(number) > limit:
        return None
    return number.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def log_temple_event(
    *,
    request,
    temple,
    event_type,
    user_lat=None,
    user_lng=None,
):
    """
    Record a temple analytics event. Analytics must never break the screen
    the user asked for, so a failure here is logged and ignored.
    """
    from .models import TempleAnalyticsView

    latitude = _coordinate(user_lat, 90)
    longitude = _coordinate(user_lng, 180)
    if latitude is None or longitude is None:
        latitude = longitude = None

    try:
        TempleAnalyticsView.objects.create(
            user=request.user if request.user.is_authenticated else None,
            temple=temple,
            event_type=event_type,
            user_latitude=latitude,
            user_longitude=longitude,
        )
    except Exception:  # noqa: BLE001 - analytics is best effort
        logger.exception("Could not record temple %s event.", event_type)
