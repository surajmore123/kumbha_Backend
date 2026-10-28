"""Coordinate validation, distances and Google Maps links."""

import math
from urllib.parse import urlencode


def valid_coordinates(latitude, longitude) -> bool:
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return False
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return False
    # (0, 0) is the default of an unfilled form, not a real place here.
    return not (lat == 0 and lng == 0)


def map_links(latitude, longitude) -> dict[str, str | None]:
    """Search and directions URLs, or None values for invalid coordinates."""
    if not valid_coordinates(latitude, longitude):
        return {"map_url": None, "directions_url": None}
    coordinates = f"{float(latitude):.6f},{float(longitude):.6f}"
    return {
        "map_url": "https://www.google.com/maps/search/?"
        + urlencode({"api": 1, "query": coordinates}),
        "directions_url": "https://www.google.com/maps/dir/?"
        + urlencode({"api": 1, "destination": coordinates}),
    }


def distance_km(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance (straight line, not a route distance)."""
    lat1, lng1, lat2, lng2 = map(math.radians, map(float, (lat1, lng1, lat2, lng2)))
    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(a))
