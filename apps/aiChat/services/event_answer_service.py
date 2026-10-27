
from apps.aiChat.services.event_service import (
    get_upcoming_verified_events,
)
from apps.aiChat.services.gemini_service import generate_reply


def answer_event_question(question: str) -> dict:
    """Answer event questions using published, verified database records."""

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must be a non-empty string.")

    events = get_upcoming_verified_events(limit=50)

    if not events:
        return {
            "answer": (
                "I couldn't find any upcoming published and verified "
                "events in the available database."
            ),
            "sources": [],
        }

    event_lines = []

    for event in events:
        event_lines.append(
            f"Event: {event['name']}\n"
            f"Date: {event['date']}\n"
            f"Start time: {event['start_time'] or 'Not specified'}\n"
            f"End time: {event['end_time'] or 'Not specified'}\n"
            f"Location: {event['location']}\n"
            f"Description: {event['description']}\n"
            f"Database source: {event['data_source']}\n"
            f"Record ID: {event['id']}"
        )

    context = "\n\n".join(event_lines)

    prompt = f"""
You are the KumbhaPath event information assistant.

Answer the user's question using only the event records below.

Rules:
- Do not invent dates, times, locations, or event details.
- State clearly when a time is not specified.
- Do not describe a database record as independently confirmed
  by an official authority.
- If the records do not answer the question, say so.
- Use concise, clear language.

Event records:
{context}

User question:
{question.strip()}
"""

    answer = generate_reply(prompt)

    return {
        "answer": answer,
        "sources": [
            f"event:{event['id']}"
            for event in events
        ],
    }
