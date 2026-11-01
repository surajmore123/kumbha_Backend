"""
Walking routes from Google's Routes API, through the server so the key isn't in
the app and the destination is always one the requester may reach.

Distances and times come only from the provider. Coordinates are never logged
or stored, and neither is the provider's error text.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
_FIELDS = "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline"
_TIMEOUT = 10


class RoutingUnavailable(Exception):
    pass


def _waypoint(latitude, longitude):
    return {"location": {"latLng": {"latitude": float(latitude), "longitude": float(longitude)}}}


def walking_route(origin, destination):
    """`origin` and `destination` are (latitude, longitude). Returns the
    provider's distance, duration and polyline, or raises RoutingUnavailable."""
    key = settings.GOOGLE_ROUTES_API_KEY
    if not key:
        raise RoutingUnavailable
    try:
        response = requests.post(
            _URL,
            json={"origin": _waypoint(*origin), "destination": _waypoint(*destination), "travelMode": "WALK"},
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": _FIELDS},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        route = response.json()["routes"][0]
        return {
            "distance_m": int(route["distanceMeters"]),
            "duration_s": int(str(route["duration"]).rstrip("s")),
            "polyline": route["polyline"]["encodedPolyline"],
        }
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning("Routing failed (%s).", type(exc).__name__)
        raise RoutingUnavailable from exc
