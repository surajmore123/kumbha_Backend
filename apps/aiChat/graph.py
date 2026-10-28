"""
Guru AI conversation graph.

    START → understand → (route → gather →) compose → END

- understand: speech recognition for voice messages and OCR for scanned
  PDFs (the only steps that turn an attachment into text).
- route: deterministic intent rules (`intent_service`); a question can
  need several tools at once.
- gather: read-only tools — temples and navigation, events, live crowd
  and incidents, the knowledge base, the uploaded document, the image.
- compose: one grounded model call, or a fixed reply when the evidence
  is missing or processing failed.

The graph never touches the request, storage of new files or the chat
tables; `services.chat_orchestrator` does that around it. Every model
call uses the time left in the request budget (`deadline`).
"""

import logging
import re
import time
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from apps.aiChat import ai_config, messages
from apps.aiChat.attachments import documents as document_tools
from apps.aiChat.attachments import storage
from apps.aiChat.rag.knowledge_service import search_documents
from apps.aiChat.services import (
    answer_composer,
    crowd_service,
    event_service,
    intent_service,
    temple_service,
)
from apps.aiChat.services.gemini_service import GeminiServiceError
from apps.aiChat.services.language_service import (
    english_for_search,
    fixed_message,
    localize,
    needs_model_language_help,
)
from apps.aiChat.services.ocr_service import ocr_available, ocr_pdf
from apps.aiChat.services.transcription_service import transcribe_audio

logger = logging.getLogger(__name__)

# Processing outcomes that end the turn with a fixed reply.
TERMINAL_STATUSES = {
    "no_speech", "audio_failed", "document_scanned_no_ocr",
    "document_failed", "document_empty",
}


class ChatState(TypedDict, total=False):
    # Existing fields (kept for compatibility).
    question: str
    answer: str
    sources: list[str]
    route: str
    temples: list[dict]

    # Request.
    user_id: str
    user_message: str
    language: str             # reply language (ISO 639-1)
    language_info: dict       # messages.LanguageInfo fields
    app_language: str         # the app's UI language: fallback only
    location: dict | None
    attachment: dict | None   # prepared upload: kind, mime_type, data, name, document
    history: dict             # history_service.build_context()
    deadline: float           # time.monotonic() budget end

    # Produced by the graph.
    transcript: dict | None
    search_text: str          # question (+ English version) used by tools
    temple_mode: str | None   # matched | context | nearby | list
    event_mode: str | None    # upcoming | recent | context
    intents: list[str]
    evidence: dict
    events: list[dict]
    crowd: dict | None
    citations: list[dict]
    status: str               # ok | degraded | error | TERMINAL_STATUSES
    errors: list[str]


def _time_left(state: ChatState) -> float | None:
    deadline = state.get("deadline")
    return None if deadline is None else deadline - time.monotonic()


# ---- understand ---------------------------------------------------------------

def understand(state: ChatState) -> dict:
    attachment = state.get("attachment") or {}
    typed = (state.get("user_message") or "").strip()
    updates: dict = {"question": typed, "status": "ok", "errors": []}

    if attachment.get("kind") == "audio":
        try:
            heard = transcribe_audio(
                attachment["data"], attachment["mime_type"], timeout=_time_left(state),
            )
        except GeminiServiceError as exc:
            logger.warning("Transcription failed (%s).", type(exc).__name__)
            return {**updates, "status": "audio_failed", "errors": ["transcription_failed"]}
        updates["transcript"] = {
            "text": heard.text,
            "language": heard.language,
            "speech_detected": heard.speech_detected,
        }
        if heard.speech_detected:
            updates["question"] = f"{typed}\n{heard.text}".strip()
            if not (state.get("language_info") or {}).get("explicit"):
                # Answer in the language that was spoken.
                spoken = messages.analyze_language(heard.text, state.get("app_language"))
                if spoken.source in ("app", "default") and heard.language in messages.LANGUAGE_NAMES:
                    spoken = messages.LanguageInfo(heard.language)
                updates["language"] = spoken.code
                updates["language_info"] = {
                    "code": spoken.code,
                    "romanized": spoken.romanized,
                    "explicit": spoken.explicit,
                    "source": "speech",
                }
        elif typed:
            # No speech, but a typed question about the sound itself
            # ("which mantra is this?"): let the model hear the audio.
            updates["attachment"] = {**attachment, "audio_direct": True}
        else:
            updates["status"] = "no_speech"

    if attachment.get("kind") == "document":
        document = attachment["document"]
        if document.scanned:
            if ocr_available(document.page_count):
                try:
                    pages = ocr_pdf(attachment["data"], timeout=_time_left(state))
                    document_tools.apply_ocr_pages(document, pages)
                except GeminiServiceError as exc:
                    logger.warning("OCR failed (%s).", type(exc).__name__)
                    return {**updates, "status": "document_failed", "errors": ["ocr_failed"]}
            else:
                return {**updates, "status": "document_scanned_no_ocr"}
        if not document.sections:
            updates["status"] = "document_empty"

    return updates


def after_understand(state: ChatState) -> Literal["route", "compose"]:
    return "compose" if state.get("status") in TERMINAL_STATUSES else "route"


# ---- route --------------------------------------------------------------------

def _search_text(state: ChatState, question: str) -> str:
    """
    Text the tools match against. Keyword rules and temple names cover
    English, Hindi and Marathi; for other languages an English version is
    added so a Gujarati or Tamil question reaches the same tools.
    """
    code = (state.get("language_info") or {}).get("code") or state.get("language") or "en"
    if question.strip() and needs_model_language_help(code):
        english = english_for_search(question, timeout=_time_left(state))
        if english:
            return f"{question}\n{english}"
    return question


def route_question(state: ChatState) -> dict:
    question = _search_text(state, state.get("question") or "")
    attachment = state.get("attachment") or {}
    mentions_temple = False
    if question.strip():
        try:
            names = temple_service.Temple.objects.filter(
                is_active=True, del_flag=0,
            ).values_list("name", flat=True)
            mentions_temple = bool(temple_service.match_temple_names(question, names))
        except Exception:  # noqa: BLE001 - routing must not fail on the DB
            logger.exception("Temple name lookup failed during routing.")
    intents = intent_service.detect_intents(
        question,
        has_image=attachment.get("kind") == "image",
        has_document=attachment.get("kind") == "document",
        mentions_temple=mentions_temple,
        context=state.get("history"),
    )
    return {
        "intents": intents,
        "route": intent_service.primary_route(intents),
        "search_text": question,
    }


# ---- gather -------------------------------------------------------------------

_ORDINALS = {
    "first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2,
    "पहला": 0, "पहले": 0, "पहिला": 0, "पहिल्या": 0, "दूसरा": 1, "दूसरे": 1,
    "दुसरा": 1, "दुसऱ्या": 1, "तीसरा": 2, "तिसरा": 2,
}
_RECENT_CHANGE = re.compile(
    r"chang|updat|postpon|reschedul|cancel|बदल|स्थगित|रद्द", re.I,
)
_SNAN = re.compile(r"snan|स्नान", re.I)


def _ordinal(question: str) -> int | None:
    lowered = question.lower()
    for word, index in _ORDINALS.items():
        if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lowered) or (
            not word.isascii() and word in lowered
        ):
            return index
    return None


def _pick(items: list[dict], index: int | None) -> list[dict]:
    if index is None or index >= len(items):
        return items
    return [items[index]]


def _origin(state: ChatState) -> tuple | None:
    location = state.get("location") or None
    if location:
        return (location["latitude"], location["longitude"])
    return None


def _gather_temples(state, evidence, question, context):
    origin = _origin(state)
    temples = temple_service.find_temples_in_question(question, limit=5, origin=origin)
    mode = "matched"
    if not temples and context.get("last_temple_ids") and intent_service.is_follow_up(question):
        temples = _pick(
            temple_service.get_temples_by_ids(context["last_temple_ids"], origin),
            _ordinal(question),
        )
        mode = "context"
    if not temples and origin:
        temples = temple_service.nearest_temples(*origin, limit=5)
        mode = "nearby"
    if not temples and intent_service.TEMPLE in (state.get("intents") or []) and not _is_specific(question):
        temples = temple_service.list_temples(limit=8)
        mode = "list"
    evidence["temples"] = temples
    evidence["temple_mode"] = mode


def _is_specific(question: str) -> bool:
    """A question naming a place we couldn't match shouldn't get a generic list."""
    return bool(re.search(r"\b[A-Z][a-z]{3,}\b", question)) and not re.search(
        r"\b(which|what|list|all|any|some|best|famous|nearby|near me)\b",
        question.lower(),
    )


def _gather_events(state, evidence, question, context):
    if _RECENT_CHANGE.search(question):
        events, mode = event_service.get_recently_updated_events(), "recent"
    elif context.get("last_event_ids") and intent_service.is_follow_up(question) and _ordinal(question) is not None:
        events = _pick(event_service.get_events_by_ids(context["last_event_ids"]), _ordinal(question))
        mode = "context"
    elif _SNAN.search(question):
        events, mode = event_service.get_upcoming_verified_events(limit=10, category="SNAN"), "upcoming"
        if not events:
            events = event_service.get_upcoming_verified_events(limit=20)
    else:
        events, mode = event_service.get_upcoming_verified_events(limit=20), "upcoming"
    evidence["events"] = events
    evidence["event_mode"] = mode


def _gather_crowd(state, evidence, question, types=None):
    zone_ids = crowd_service.find_zones_in_question(question) or None
    if zone_ids is None and evidence.get("temples") and evidence.get("temple_mode") in ("matched", "context"):
        near = []
        for temple in evidence["temples"]:
            near.extend(crowd_service.zones_near(temple["latitude"], temple["longitude"]))
        zone_ids = list(dict.fromkeys(near))
        if not zone_ids:
            evidence.setdefault("notes", []).append(
                "No crowd monitoring zone covers the temple(s) above, so there is "
                "no crowd measurement for them."
            )
    if zone_ids is None and _origin(state):
        zone_ids = crowd_service.zones_near(*_origin(state)) or None
    zones = crowd_service.get_zone_crowd(zone_ids) if zone_ids != [] else []
    evidence["crowd"] = zones
    evidence["crowd_freshness"] = crowd_service.freshness(zones)
    evidence["incidents"] = crowd_service.get_active_incidents(
        zone_ids if zone_ids else None, types=types,
    )


def _gather_knowledge(evidence, question):
    results = [
        r for r in search_documents(question, limit=5)
        if r["score"] >= ai_config.rag_min_score()
    ]
    evidence["knowledge"] = results


def _gather_document(state, evidence, question, context):
    attachment = state.get("attachment") or {}
    if attachment.get("kind") == "document":
        document = attachment["document"]
    elif context.get("document"):
        stored = storage.load_json(state.get("user_id"), context["document"]["extract_key"])
        if not stored:
            evidence.setdefault("notes", []).append(
                "The document referred to is no longer available."
            )
            return
        document = document_tools.ExtractedDocument.from_dict(stored)
    else:
        return
    chunks = document_tools.chunk_document(document)
    selected = document_tools.select_chunks(chunks, question)
    evidence["document"] = {
        "name": document.name,
        "truncated": document.truncated,
        "ocr_used": document.ocr_used,
        "selected": len(selected) < len(chunks),
        "chunks": [{"text": c.text, "location": c.location} for c in selected],
    }


def _gather_image(state, evidence, context):
    attachment = state.get("attachment") or {}
    if attachment.get("kind") == "image":
        evidence["image"] = {"data": attachment["data"], "mime_type": attachment["mime_type"]}
        return
    previous = context.get("image")
    if previous:
        data = storage.load_bytes(
            state.get("user_id"), previous["storage_key"], ai_config.max_image_bytes(),
        )
        if data:
            evidence["image"] = {"data": data, "mime_type": previous["mime_type"]}


def gather(state: ChatState) -> dict:
    question = state.get("search_text") or state.get("question") or ""
    intents = state.get("intents") or []
    context = state.get("history") or {}
    evidence: dict = {}
    errors = list(state.get("errors") or [])
    if state.get("attachment", {}) and state["attachment"].get("audio_direct"):
        evidence["audio"] = {
            "data": state["attachment"]["data"],
            "mime_type": state["attachment"]["mime_type"],
        }

    steps = []
    if intent_service.DOCUMENT in intents:
        steps.append(("document", lambda: _gather_document(state, evidence, question, context)))
    if intent_service.IMAGE in intents:
        steps.append(("image", lambda: _gather_image(state, evidence, context)))
    if intent_service.TEMPLE in intents:
        steps.append(("temples", lambda: _gather_temples(state, evidence, question, context)))
    if intent_service.EVENTS in intents:
        steps.append(("events", lambda: _gather_events(state, evidence, question, context)))
    if intent_service.CROWD in intents:
        steps.append(("crowd", lambda: _gather_crowd(state, evidence, question)))
    if intent_service.SAFETY in intents and intent_service.CROWD not in intents:
        steps.append((
            "incidents",
            lambda: _gather_crowd(state, evidence, question, types=["MEDICAL", "SECURITY", "CROWD"]),
        ))
    wants_knowledge = (
        intent_service.RAG in intents
        or intent_service.SAFETY in intents
        # A real question that matched no tool may still be in the
        # knowledge base ("who started this mela?").
        or (intents == [intent_service.DIRECT] and intent_service.is_substantive(question))
    )
    if wants_knowledge and question.strip():
        steps.append(("knowledge", lambda: _gather_knowledge(evidence, question)))

    def run(name, step):
        try:
            step()
        except Exception as exc:  # noqa: BLE001 - one tool must not sink the answer
            logger.error("Tool %s failed (%s).", name, type(exc).__name__)
            errors.append(f"{name}_unavailable")
            evidence.setdefault("notes", []).append(
                f"The {name} data source is temporarily unavailable; do not guess its contents."
            )

    for name, step in steps:
        run(name, step)

    # No event records: the knowledge base may still have the published
    # schedule (e.g. the Simhastha bathing dates).
    if (
        intent_service.EVENTS in intents
        and not evidence.get("events")
        and "knowledge" not in evidence
        and question.strip()
    ):
        run("knowledge", lambda: _gather_knowledge(evidence, question))

    if intent_service.TEMPLE in intents and not evidence.get("temples") and "temples" in evidence:
        evidence.setdefault("notes", []).append(
            "The place the user asked about is not in the KumbhaPath temple database, so "
            "there are no app directions or crowd data for it. You may describe it from "
            "well-established general knowledge."
        )
    if intent_service.RAG in intents or intents == [intent_service.DIRECT]:
        evidence.setdefault("notes", []).append(
            _GENERAL_KNOWLEDGE_NOTE if not evidence.get("knowledge") else _FILL_GAPS_NOTE
        )

    return {
        "evidence": evidence,
        "errors": errors,
        "temples": evidence.get("temples") or [],
        "events": evidence.get("events") or [],
        "temple_mode": evidence.get("temple_mode"),
        "event_mode": evidence.get("event_mode"),
    }


# ---- compose ------------------------------------------------------------------

_GENERAL_KNOWLEDGE_NOTE = (
    "No knowledge-base passage matched this question. Answer it helpfully from "
    "well-established general knowledge about the Kumbh Mela, Nashik, Trimbakeshwar, "
    "Hindu rituals and pilgrim practice (history, meaning, what happens, where it is "
    "traditionally held). Do not open with what you lack. Only for details that change "
    "(exact upcoming dates, daily timings, fees, closures) say they should be confirmed "
    "locally or with official announcements."
)

_FILL_GAPS_NOTE = (
    "The knowledge-base passages may not cover this question fully. Use what they "
    "say, and answer the rest from well-established general knowledge about the "
    "Kumbh Mela, Nashik, Trimbakeshwar, Hindu rituals and pilgrim practice (for "
    "example: in Nashik the Godavari is revered as the Dakshin Ganga, and its aarti "
    "is traditionally performed at Ramkund). Never answer only that the passages "
    "don't mention it. Say that changing details such as exact timings should be "
    "confirmed locally."
)

# Fixed replies only where nothing can stand in for live data: no event
# records and nothing in the knowledge base, or no crowd measurement.
_EMPTY_REPLIES = {
    intent_service.EVENTS: "no_events",
    intent_service.CROWD: "no_crowd",
}
_FAILED_REPLIES = {"image": "image_failed", "audio": "audio_failed", "document": "document_failed"}


def _has_evidence(evidence: dict) -> bool:
    return any(
        evidence.get(key)
        for key in ("temples", "events", "knowledge", "document", "image", "audio", "incidents")
    ) or any(z.get("calculated_at") for z in evidence.get("crowd") or [])


def compose(state: ChatState) -> dict:
    language = state.get("language") or "en"
    status = state.get("status") or "ok"
    evidence = state.get("evidence") or {}
    intents = state.get("intents") or []
    attachment_kind = (state.get("attachment") or {}).get("kind")
    result = {"evidence": evidence, "citations": [], "sources": []}

    if status in TERMINAL_STATUSES:
        key = "document_failed" if status == "document_failed" else status
        return {**result, "answer": fixed_message(key, language, timeout=_time_left(state)),
                "route": attachment_kind or intent_service.DIRECT}

    # Live data (events, crowd) with nothing found: a fixed reply, since
    # general knowledge can't stand in for it. A knowledge-base lookup that
    # also came back empty doesn't change that.
    core = set(intents) - {intent_service.RAG}
    domain = [i for i in intents if i in _EMPTY_REPLIES]
    other_notes = [
        n for n in evidence.get("notes") or []
        if n not in (_GENERAL_KNOWLEDGE_NOTE, _FILL_GAPS_NOTE)
    ]
    if (
        domain
        and core <= set(_EMPTY_REPLIES)
        and not _has_evidence(evidence)
        and not other_notes
    ):
        return {**result, "answer": fixed_message(
            _EMPTY_REPLIES[domain[0]], language, timeout=_time_left(state),
        )}

    sources, citations = answer_composer.build_citations(evidence)
    try:
        answer = answer_composer.strip_urls(
            answer_composer.compose_answer({**state, "time_left": _time_left(state)})
        )
        status = "degraded" if state.get("errors") else "ok"
    except GeminiServiceError as exc:
        status = "error"
        answer = None if attachment_kind else answer_composer.fallback_answer(evidence, language, exc)
        if answer:
            answer = localize(answer, language, timeout=_time_left(state))
        if answer:
            status = "degraded"
        else:
            key = _FAILED_REPLIES.get(attachment_kind) or (
                "busy" if type(exc).__name__ == "GeminiQuotaError" else "unavailable"
            )
            answer = fixed_message(key, language, timeout=_time_left(state))
            sources, citations = [], []

    footer = answer_composer.crowd_footer(evidence, language)
    if footer and status != "error":
        footer = localize(footer, language, timeout=_time_left(state))
        answer = f"{answer}\n\n{footer}"

    return {
        **result,
        "answer": answer,
        "sources": sources,
        "citations": citations,
        "status": status,
        "crowd": {
            "zones": evidence.get("crowd") or [],
            "incidents": evidence.get("incidents") or [],
            "freshness": evidence.get("crowd_freshness"),
        } if "crowd" in evidence or evidence.get("incidents") else None,
    }


# ---- graph ----------------------------------------------------------------------

builder = StateGraph(ChatState)

builder.add_node("understand", understand)
builder.add_node("route_question", route_question)
builder.add_node("gather", gather)
builder.add_node("compose", compose)

builder.add_edge(START, "understand")
builder.add_conditional_edges(
    "understand",
    after_understand,
    {"route": "route_question", "compose": "compose"},
)
builder.add_edge("route_question", "gather")
builder.add_edge("gather", "compose")
builder.add_edge("compose", END)

chat_graph = builder.compile()
