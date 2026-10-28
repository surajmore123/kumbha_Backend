"""
Deterministic intent detection for Guru AI.

Rules are explicit and testable. A question can have several intents
(e.g. a temple plus its crowd and directions); each intent selects a
read-only tool in the graph. Weak words like "when" or "today" only count
when the question is about events or follows an event answer, so "when
does the temple open?" is not sent to the event schedule.
"""

import re

TEMPLE = "temple"
EVENTS = "events"
CROWD = "crowd"
SAFETY = "safety"
RAG = "rag"
DOCUMENT = "document"
IMAGE = "image"
DIRECT = "direct"

# Order used to pick the single legacy `route` value.
PRIORITY = (DOCUMENT, IMAGE, TEMPLE, EVENTS, CROWD, SAFETY, RAG, DIRECT)

_TEMPLE_WORDS = (
    "temple", "mandir", "jyotirling", "darshan", "how can i reach",
    "how to reach", "how do i reach", "directions", "navigate", "google maps",
    "route to", "way to", "मंदिर", "दर्शन", "कैसे पहुँच", "कैसे पहुंच",
    "कसे पोहोच", "रस्ता", "मार्ग",
)
_EVENT_WORDS = (
    "event", "schedule", "amrit snan", "shahi snan", "snan", "snaan",
    "amrut snan", "flag hoisting",
    "dhwajarohan", "kumbh begins", "upcoming", "parva", "programme",
    "program", "important date", "important day", "calendar", "timetable",
    "muhurat", "peshwai", "कार्यक्रम", "स्नान", "शाही", "अमृत", "ध्वजारोहण",
    "पर्व", "वेळापत्रक", "समय सारणी", "तिथि", "तिथी", "मुहूर्त",
)
_WEAK_EVENT_WORDS = (
    "when", "date", "today", "tomorrow", "next", "कब", "कधी", "तारीख",
    "आज", "उद्या", "कल",
)
_CROWD_WORDS = (
    "crowd", "crowded", "rush", "busy", "occupancy", "how many people",
    "incident", "traffic", "jam", "congestion", "alert", "भीड़", "भीड",
    "गर्दी", "ट्रैफिक", "वाहतूक", "कोंडी", "जाम",
)
_SAFETY_WORDS = (
    "emergency", "help", "lost", "missing", "police", "ambulance", "medical",
    "injured", "injury", "hospital", "first aid", "safety", "safe", "stampede",
    "fire", "आपातकाल", "मदद", "खो गया", "खो गई", "हरवल", "पोलीस", "पुलिस",
    "रुग्णवाहिका", "एम्बुलेंस", "सुरक्षा", "अपघात", "दुर्घटना",
)
_KNOWLEDGE_WORDS = (
    "kumbh", "godavari", "ghat", "pilgrim", "nashik", "ritual", "history",
    "significance", "facility", "facilities", "toilet", "parking",
    "accessib", "wheelchair", "lost and found", "rules", "guideline",
    "faq", "ramkund", "panchavati", "simhastha", "mela", "akhara", "akhada",
    "sadhu", "naga", "ganga", "trimbak", "kushavarta", "mythology",
    "legend", "story", "tradition", "custom", "kumbha",
    "कुंभ", "गोदावरी", "घाट", "इतिहास", "महत्व", "महत्त्व", "रामकुंड",
    "पंचवटी", "सुविधा", "नियम", "सिंहस्थ", "मेला", "मेळा", "आखाडा", "अखाड़ा",
    "साधु", "गंगा", "परंपरा", "कथा",
)
# Rituals and practices: background knowledge, not database events.
_RITUAL_WORDS = (
    "aarti", "aarthi", "aarati", "arti", "mahaarti", "maha aarti", "puja",
    "pooja", "abhishek", "bhajan", "kirtan", "yatra", "palkhi", "procession",
    "holy dip", "holy bath", "bathing", "offering", "prasad", "darshan time",
    "आरती", "पूजा", "अभिषेक", "भजन", "कीर्तन", "यात्रा", "पालखी", "मिरवणूक",
    "प्रसाद",
)
_DOCUMENT_WORDS = (
    "document", "pdf", "file", "notice", "letter", "attachment", "page",
    "sheet", "spreadsheet", "दस्तावेज़", "दस्तावेज", "दस्तऐवज", "फाइल",
    "फ़ाइल", "सूचना", "पत्र",
)
_IMAGE_WORDS = (
    "image", "photo", "picture", "pic", "screenshot", "फोटो", "चित्र", "तस्वीर",
)
_REFERENCE_WORDS = (
    "that", "this", "it", "there", "those", "first", "second", "third",
    "last one", "same", "what about", "and the", "उस", "वह", "वहाँ", "वहां",
    "पहला", "पहले", "ते", "तो", "तिथे", "पहिल", "त्या",
)

_QUESTION_WORDS = (
    "what", "when", "where", "how", "which", "who", "is it", "क्या", "कब",
    "कहाँ", "कहां", "कैसे", "कौन", "काय", "कधी", "कुठे", "कसे", "कोण",
)

_NORMALIZE = re.compile(r"\s+")


def _has(text: str, words) -> bool:
    """
    Latin words of five or more letters match as prefixes ("pilgrim"
    matches "pilgrims"); shorter ones as whole words with an optional
    plural "s" ("date" matches "dates", but "it" doesn't match "item").
    Devanagari words match as substrings.
    """
    for word in words:
        if word.isascii():
            tail = "" if len(word) >= 5 else r"s?(?![a-z])"
            if re.search(rf"(?<![a-z]){re.escape(word)}{tail}", text):
                return True
        elif word in text:
            return True
    return False


def is_follow_up(question: str) -> bool:
    """
    A question pointing back at the previous answer ("how do I get there?",
    "and the first one?", "tomorrow?"). A new question that merely starts
    with "where"/"when" is not a follow-up.
    """
    text = _NORMALIZE.sub(" ", question.lower()).strip()
    if _has(text, _REFERENCE_WORDS):
        return True
    return len(text.split()) <= 3 and (
        "?" in text or _has(text, _QUESTION_WORDS)
    )


def is_substantive(question: str) -> bool:
    """A real question (not "ok", "thanks", "hi")."""
    text = _NORMALIZE.sub(" ", question.lower()).strip()
    return len(text.split()) >= 3 and ("?" in text or _has(text, _QUESTION_WORDS))


def detect_intents(
    question: str,
    *,
    has_image: bool = False,
    has_document: bool = False,
    mentions_temple: bool = False,
    context: dict | None = None,
) -> list[str]:
    context = context or {}
    text = _NORMALIZE.sub(" ", (question or "").lower()).strip()
    intents: list[str] = []

    if has_document or (
        context.get("document")
        and (
            _has(text, _DOCUMENT_WORDS)
            or (context.get("last_route") == DOCUMENT and is_follow_up(text))
        )
    ):
        intents.append(DOCUMENT)
    if has_image or (context.get("image") and _has(text, _IMAGE_WORDS)):
        intents.append(IMAGE)

    if mentions_temple or _has(text, _TEMPLE_WORDS):
        intents.append(TEMPLE)
    if _has(text, _EVENT_WORDS):
        intents.append(EVENTS)
    if _has(text, _CROWD_WORDS):
        intents.append(CROWD)
    if _has(text, _SAFETY_WORDS):
        intents.append(SAFETY)

    domain = [i for i in intents if i not in (DOCUMENT, IMAGE)]
    knowledge = _has(text, _KNOWLEDGE_WORDS)
    # "Important dates for Kumbh", "when is the Kumbh": the event schedule.
    if EVENTS not in intents and _has(text, _WEAK_EVENT_WORDS) and (
        knowledge or (not domain and context.get("last_route") == EVENTS)
    ):
        intents.append(EVENTS)
    if knowledge or _has(text, _RITUAL_WORDS):
        intents.append(RAG)

    # "What about the second one?" continues the previous topic.
    if not intents and text and is_follow_up(text):
        previous = [
            i for i in context.get("last_intents") or [context.get("last_route")]
            if i in (TEMPLE, EVENTS, CROWD, SAFETY, RAG)
        ]
        intents.extend(previous)

    return intents or [DIRECT]


def primary_route(intents: list[str]) -> str:
    for route in PRIORITY:
        if route in intents:
            return route
    return DIRECT
