
import re

from django.db.models import Q

from apps.aiChat.services.geo import distance_km, map_links, valid_coordinates
from apps.temples.models import Temple

# Spellings pilgrims use (romanised and Devanagari) mapped to text that
# appears in the stored temple name. They only help find database rows;
# a temple that isn't in the database is never returned.
TEMPLE_ALIASES = {
    "trimbak": "trimbakeshwar",
    "tryambak": "trimbakeshwar",
    "tryambakeshwar": "trimbakeshwar",
    "trimbakeshwar": "trimbakeshwar",
    "त्र्यंबकेश्वर": "trimbakeshwar",
    "त्रयंबकेश्वर": "trimbakeshwar",
    "त्र्यम्बकेश्वर": "trimbakeshwar",
    "त्र्यंबक": "trimbakeshwar",
    "kalaram": "kala rama",
    "kala ram": "kala rama",
    "काळाराम": "kala rama",
    "कालाराम": "kala rama",
    "कपालेश्वर": "kapaleshwar",
    "नवश्या": "navshya",
    "सोमेश्वर": "someshwar",
    "कालिका": "kalika",
    "बालाजी": "balaji",
    "venkatesh": "vyankatesh",
    "व्यंकटेश": "vyankatesh",
    "वेंकटेश": "vyankatesh",
}

_GENERIC_NAME_WORDS = {
    "temple", "mandir", "jyotirling", "jyotirlinga", "shree", "shri",
    "swamy", "swami", "nashik", "devasthan",
}

_NORMALIZE = re.compile(r"[^a-z0-9ऀ-ॿ]+")


def _normalize(text: str) -> str:
    return _NORMALIZE.sub(" ", (text or "").lower()).strip()


def build_temple_map_links(latitude: float, longitude: float) -> dict:
    """Build Google Maps search and directions URLs."""
    return map_links(latitude, longitude)


def _active_temples():
    return Temple.objects.filter(is_active=True, del_flag=0)


def _temple_dict(temple: Temple, origin: tuple | None = None) -> dict:
    latitude = float(temple.latitude)
    longitude = float(temple.longitude)
    result = {
        "id": str(temple.temple_id),
        "name": temple.name,
        "description": temple.description or "",
        "city": temple.city,
        "state": temple.state,
        "latitude": latitude,
        "longitude": longitude,
        "image_url": temple.image_url,
        # An advisory set by admins, not a live measurement.
        "crowd_level": temple.crowd_level,
        "crowd_message": temple.crowd_message or "",
        "crowd_level_source": "admin_advisory",
        **map_links(latitude, longitude),
    }
    if origin and valid_coordinates(latitude, longitude):
        result["distance_km"] = round(
            distance_km(origin[0], origin[1], latitude, longitude), 2,
        )
    return result


def find_temples(query: str, limit: int = 5) -> list[dict]:
    """Find active temples by name, description, or city."""

    if not isinstance(query, str) or not query.strip():
        raise ValueError("Temple search query must not be empty.")

    if not 1 <= limit <= 20:
        raise ValueError("Limit must be between 1 and 20.")

    temples = (
        _active_temples()
        .filter(models_q(query.strip()))
        .order_by("name")[:limit]
    )
    return [_temple_dict(temple) for temple in temples]


def models_q(query: str):
    """Build a case-insensitive search across temple text fields."""
    return (
        Q(name__icontains=query)
        | Q(description__icontains=query)
        | Q(city__icontains=query)
    )


def match_temple_names(question: str, names) -> list[str]:
    """Stored temple names mentioned in the question (aliases included)."""
    question_normalized = _normalize(question)
    question_words = set(question_normalized.split())
    padded_question = f" {question_normalized} "

    targets = [
        target
        for alias, target in TEMPLE_ALIASES.items()
        if f" {_normalize(alias)} " in padded_question
        or (not alias.isascii() and _normalize(alias) in question_normalized)
    ]

    matched = []
    for name in names:
        name_normalized = _normalize(name)
        distinctive = [
            word
            for word in name_normalized.split()
            if len(word) >= 5 and word not in _GENERIC_NAME_WORDS
        ]
        if (
            f" {name_normalized} " in padded_question
            or any(word in question_words for word in distinctive)
            or any(target in name_normalized for target in targets)
        ):
            matched.append(name)
    return matched


def find_temples_in_question(
    question: str,
    limit: int = 5,
    origin: tuple | None = None,
) -> list[dict]:
    """Find temples mentioned within a natural-language question."""

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must not be empty.")

    if not 1 <= limit <= 20:
        raise ValueError("Limit must be between 1 and 20.")

    names = list(_active_temples().values_list("name", flat=True))
    matched = match_temple_names(question, names)
    if not matched:
        return []

    temples = _active_temples().filter(name__in=matched[:limit]).order_by("name")
    return [_temple_dict(temple, origin) for temple in temples[:limit]]


def get_temples_by_ids(ids: list[str], origin: tuple | None = None) -> list[dict]:
    """Re-read temples referenced earlier in the conversation."""
    clean = [str(i) for i in ids if i][:10]
    if not clean:
        return []
    try:
        temples = list(_active_temples().filter(temple_id__in=clean))
    except Exception:  # noqa: BLE001 - malformed UUIDs from old metadata
        return []
    order = {value: index for index, value in enumerate(clean)}
    temples.sort(key=lambda t: order.get(str(t.temple_id), 99))
    return [_temple_dict(temple, origin) for temple in temples]


def nearest_temples(latitude, longitude, limit: int = 5) -> list[dict]:
    """Active temples ordered by straight-line distance from a point."""
    if not valid_coordinates(latitude, longitude):
        return []
    origin = (float(latitude), float(longitude))
    temples = [_temple_dict(t, origin) for t in _active_temples()]
    temples = [t for t in temples if "distance_km" in t]
    temples.sort(key=lambda t: t["distance_km"])
    return temples[:limit]


def list_temples(limit: int = 10) -> list[dict]:
    return [_temple_dict(t) for t in _active_temples().order_by("name")[:limit]]
