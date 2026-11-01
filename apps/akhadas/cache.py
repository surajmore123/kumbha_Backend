"""Short-lived cache for public responses, emptied whenever content changes."""

from functools import wraps

from django.core.cache import cache
from rest_framework.response import Response

_TTL = 300
_VERSION_KEY = "akhadas:version"


def invalidate():
    # Old entries become unreachable and expire on their own.
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 1, None)


def cached_get(method):
    """Caches a successful GET by its full URL (which includes the language)."""

    @wraps(method)
    def wrapper(self, request, *args, **kwargs):
        version = cache.get_or_set(_VERSION_KEY, 1, None)
        key = f"akhadas:{version}:{request.get_full_path()}"
        hit = cache.get(key)
        if hit is not None:
            return Response(hit)
        response = method(self, request, *args, **kwargs)
        if response.status_code == 200:
            cache.set(key, response.data, _TTL)
        return response

    return wrapper
