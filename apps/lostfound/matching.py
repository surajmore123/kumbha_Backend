"""
Suggests which lost and found reports might describe the same person.

The score only orders a staff member's review. It proves nothing, it never
changes a case, and it's never shown to pilgrims. Each suggestion lists what
contributed, so a person can judge it.

Used: age, clothing, description, distance, time. Deliberately not used: names
(often wrong or unknown), gender, faces, photographs, religion or caste terms.

To improve it, change `SIGNALS` or `_tokens`. AI-extracted details count only
after a person has accepted them, and they feed this same review.
"""

import re
from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist

from apps.aiChat.services.geo import distance_km
from apps.lostfound.models import ACTIVE_STATUSES, CaseExtraction, CaseMatch, LostFoundCase

MINIMUM_SCORE = 35
MINIMUM_SIGNALS = 2
MAX_DISTANCE_KM = 25
MAX_DAYS_APART = 14
HIGH_CONFIDENCE = 70
MEDIUM_CONFIDENCE = 50
# A difference in these counts against a pair. Free descriptions can differ
# without disagreeing, so they only ever add to a score.
CONFLICTS = ("clothing", "age", "location", "time")
NOTICE = "A score is not proof of identity. A qualified person must review this before anything is done."

# Every word is folded to one English form so that reports in different
# languages can be compared. Common descriptive terms only.
_FOLD = {
    "सफेद": "white", "पांढरा": "white", "पांढरी": "white", "पांढरे": "white",
    "काला": "black", "काली": "black", "काळा": "black", "काळी": "black", "काळे": "black",
    "लाल": "red", "नीला": "blue", "नीली": "blue", "निळा": "blue", "निळी": "blue", "निळे": "blue",
    "हरा": "green", "हरी": "green", "हिरवा": "green", "हिरवी": "green", "हिरवे": "green",
    "पीला": "yellow", "पीली": "yellow", "पिवळा": "yellow", "पिवळी": "yellow", "पिवळे": "yellow",
    "भगवा": "saffron", "केसरी": "saffron", "orange": "saffron", "नारंगी": "saffron",
    "गुलाबी": "pink", "भूरा": "brown", "तपकिरी": "brown",
    "कुर्ता": "kurta", "सदरा": "kurta", "shirt": "shirt", "कमीज": "shirt", "शर्ट": "shirt",
    "धोती": "dhoti", "साड़ी": "saree", "साडी": "saree", "sari": "saree",
    "टोपी": "cap", "hat": "cap", "चश्मा": "glasses", "चष्मा": "glasses", "spectacles": "glasses",
    "छड़ी": "stick", "काठी": "stick", "cane": "stick", "बैग": "bag", "पिशवी": "bag",
}
_STOP = {
    "a", "an", "and", "the", "with", "wearing", "in", "on", "of", "has", "had", "is", "was", "he", "she",
    "they", "very", "some", "old", "young", "person", "boy", "girl", "man", "woman", "और", "एक", "है", "था",
    "थी", "ने", "का", "की", "के", "आणि", "आहे", "होता", "होती", "चा", "ची", "चे",
}
_WORD = re.compile(r"[\wऀ-ॿ]+", re.UNICODE)


def _tokens(*texts):
    words = set()
    for text in texts:
        for word in _WORD.findall((text or "").lower()):
            if word not in _STOP and len(word) > 1:
                words.add(_FOLD.get(word, word))
    return words


def _overlap(a, b):
    if not a or not b:
        return 0.0, []
    shared = a & b
    return len(shared) / min(len(a), len(b)), sorted(shared)


def reviewed_details(case):
    """What a person accepted from AI extraction. Unreviewed output is never used."""
    try:
        extraction = case.ai_extraction
    except ObjectDoesNotExist:
        return {}
    return extraction.reviewed_fields if extraction.review == CaseExtraction.Review.ACCEPTED else {}


def _age_range(case):
    if case.age_min is not None:
        return case.age_min, case.age_max if case.age_max is not None else case.age_min
    age = reviewed_details(case).get("approx_age")
    return (age, age) if age is not None else (None, None)


def _age(lost, found):
    lost_low, lost_top = _age_range(lost)
    found_low, found_top = _age_range(found)
    if lost_low is None or found_low is None:
        return None
    gap = max(lost_low - found_top, found_low - lost_top, 0)
    if gap > 5:
        return 0.0, "ages too far apart"
    return 1.0 - gap / 6, "age ranges overlap" if gap == 0 else f"ages within {gap} years"


def _scripts(words):
    return {"devanagari" if any("ऀ" <= letter <= "ॿ" for letter in word) else "latin" for word in words}


def _worn(case):
    return _tokens(case.clothing_description, " ".join(reviewed_details(case).get("clothing", [])))


def _clothing(lost, found):
    a, b = _worn(lost), _worn(found)
    share, shared = _overlap(a, b)
    if shared:
        return share, ", ".join(shared)
    # Words in two scripts may mean the same thing, so that's unknown, not a conflict.
    return (0.0, "described differently") if _scripts(a) & _scripts(b) else None


def _description(lost, found):
    share, shared = _overlap(
        _tokens(lost.physical_description, lost.identifying_marks),
        _tokens(found.physical_description, found.identifying_marks),
    )
    return None if not shared and share == 0 else (share, ", ".join(shared))


def _distance(lost, found):
    if lost.latitude is None or found.latitude is None:
        return None
    km = distance_km(float(lost.latitude), float(lost.longitude), float(found.latitude), float(found.longitude))
    if km > MAX_DISTANCE_KM:
        return 0.0, f"{km:.0f} km apart"
    return 1.0 - km / MAX_DISTANCE_KM, f"{km:.1f} km apart"


def _time(lost, found):
    gap = found.event_at - lost.event_at
    if gap < timedelta(hours=-6):
        return 0.0, "found before last seen"
    hours = abs(gap.total_seconds()) / 3600
    if hours > MAX_DAYS_APART * 24:
        return 0.0, "too far apart in time"
    return 1.0 - hours / (MAX_DAYS_APART * 24), f"{hours:.0f} hours apart"


# (name, points, signal). A signal returning None had nothing to compare, so it
# adds nothing and isn't counted against the pair.
SIGNALS = (
    ("clothing", 30, _clothing),
    ("age", 25, _age),
    ("description", 20, _description),
    ("location", 15, _distance),
    ("time", 10, _time),
)


def score_pair(lost, found):
    """(score out of 100, reasons, how many signals agreed)."""
    score = 0
    agreed = 0
    reasons = []
    for name, points, signal in SIGNALS:
        result = signal(lost, found)
        if result is None:
            continue
        share, detail = result
        earned = round(points * share)
        score += earned
        agreed += 1 if earned else 0
        reasons.append({"attribute": name, "points": earned, "out_of": points, "detail": detail})
    return score, reasons, agreed


def _confidence(score, conflicting):
    if conflicting:
        return "medium" if score >= HIGH_CONFIDENCE else "low"
    if score >= HIGH_CONFIDENCE:
        return "high"
    return "medium" if score >= MEDIUM_CONFIDENCE else "low"


def explain(lost, found):
    """Why a pair was suggested, for the person reviewing it. Confidence orders
    the work and doesn't say who anyone is."""
    score, reasons, _ = score_pair(lost, found)
    compared = {reason["attribute"] for reason in reasons}
    matching = [reason for reason in reasons if reason["points"]]
    conflicting = [
        reason for reason in reasons if not reason["points"] and reason["attribute"] in CONFLICTS
    ]
    missing = [name for name, _, _ in SIGNALS if name not in compared]
    parts = [f"Agrees on {', '.join(r['attribute'] for r in matching)}."] if matching else []
    if conflicting:
        parts.append(f"Differs on {', '.join(r['attribute'] for r in conflicting)}.")
    if missing:
        parts.append(f"Nothing to compare for {', '.join(missing)}.")
    return {
        "score": score,
        "confidence": _confidence(score, conflicting),
        "matching": [r["attribute"] for r in matching],
        "conflicting": [r["attribute"] for r in conflicting],
        "missing": missing,
        "explanation": " ".join(parts),
        "uses_reviewed_ai": bool(reviewed_details(lost) or reviewed_details(found)),
        "notice": NOTICE,
    }


def find_matches(case):
    """Records suggestions for this case. Changes nothing else, and leaves
    anything a person has already reviewed exactly as it is."""
    lost_type = case.case_type == LostFoundCase.Type.LOST
    others = LostFoundCase.objects.filter(
        case_type=LostFoundCase.Type.FOUND if lost_type else LostFoundCase.Type.LOST,
        status__in=ACTIVE_STATUSES,
    ).select_related("ai_extraction")
    made = []
    for other in others[:500]:
        lost, found = (case, other) if lost_type else (other, case)
        score, reasons, agreed = score_pair(lost, found)
        if score < MINIMUM_SCORE or agreed < MINIMUM_SIGNALS:
            continue
        match, created = CaseMatch.objects.get_or_create(
            lost_case=lost, found_case=found, defaults={"score": score, "reasons": reasons},
        )
        if not created and match.state == CaseMatch.State.SUGGESTED:
            match.score = score
            match.reasons = reasons
            match.save(update_fields=["score", "reasons"])
        made.append(match)
    return made
