# apps/journal/services/ai_reflection_context.py
from apps.authentication.models import User
from django.utils import timezone
from django.db.models import Count, F
from datetime import timedelta
from collections import Counter
import os
import google.generativeai as genai
from django.conf import settings


from apps.journal.models import JournalEntry, SpiritualPrinciple
from apps.crowd.models import UserZonePresence
from apps.events.models import EventAnalytics
from apps.temples.models import TempleAnalyticsView
from apps.aiChat.models import ChatMessage

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-2.5-flash")

def build_user_reflection_context(user):
    """
    Build structured, compressed context for AI Reflection.
    No LLM call here.
    """

    context = {}

    now = timezone.now()
    last_48_hours = now - timedelta(hours=48)

    # ============================================================
    # 1️⃣ MOVEMENT PATTERN (Zone Presence)
    # ============================================================

    zone_logs = (
        UserZonePresence.objects
        .filter(user=user, entered_at__gte=last_48_hours)
        .select_related("zone", "previous_zone")
        .order_by("-entered_at")[:5]
    )

    movement_summary = "No recent movement detected."

    if zone_logs.exists():
        zone_names = [z.zone.name for z in zone_logs if z.zone]
        unique_zones = set(zone_names)

        most_common_zone = Counter(zone_names).most_common(1)
        most_visited = most_common_zone[0][0] if most_common_zone else None

        movement_summary = (
            f"Visited {len(unique_zones)} zones recently. "
        )

        if most_visited:
            movement_summary += f"Spent notable time near {most_visited}. "

        last_entry = zone_logs.first()
        if last_entry and last_entry.previous_zone:
            movement_summary += (
                f"Recently moved from {last_entry.previous_zone.name} "
                f"to {last_entry.zone.name}."
            )

    context["movement_pattern"] = movement_summary

    # ============================================================
    # 2️⃣ TEMPLE ENGAGEMENT
    # ============================================================

    temple_logs = (
        TempleAnalyticsView.objects
        .filter(user=user)
        .select_related("temple")
        .order_by("-created_at")[:3]
    )

    temple_summary = "No recent temple engagement."

    if temple_logs.exists():
        actions = Counter([t.event_type for t in temple_logs])
        temples = [t.temple.name for t in temple_logs if t.temple]

        temple_summary = (
            f"Interacted with temples: {', '.join(set(temples))}. "
        )

        if actions.get("NAVIGATE"):
            temple_summary += "Actively navigated towards temples. "

        if actions.get("VIEW"):
            temple_summary += "Explored temple details."

    context["temple_engagement"] = temple_summary

    # ============================================================
    # 3️⃣ EVENT PARTICIPATION
    # ============================================================

    event_logs = (
        EventAnalytics.objects
        .filter(user=user)
        .select_related("event")
        .order_by("-created_at")[:3]
    )

    event_summary = "No recent event interaction."

    if event_logs.exists():
        event_names = [e.event.event_name for e in event_logs]
        actions = Counter([e.event_type for e in event_logs])

        event_summary = (
            f"Recently interacted with events: {', '.join(set(event_names))}. "
        )

        if actions.get("REMIND_ENABLE"):
            event_summary += "Enabled reminders for spiritual events. "

        if actions.get("DETAIL_OPEN"):
            event_summary += "Frequently explored event details."

    context["event_participation"] = event_summary

    # ============================================================
    # 4️⃣ RECENT CHAT REFLECTIONS (User Only)
    # ============================================================

    chat_messages = (
        ChatMessage.objects
        .filter(user=user, role="user", message_type="text")
        .order_by("-created_at")[:3]
    )

    chat_snippets = []

    for msg in chat_messages:
        if msg.content:
            chat_snippets.append(msg.content[:150])

    context["recent_reflections"] = chat_snippets

    # ============================================================
    # 5️⃣ EMOTIONAL PATTERN (Journal)
    # ============================================================

    journal_entries = (
        JournalEntry.objects
        .filter(user=user)
        .order_by("-created_at")[:3]
    )

    moods = [entry.mood for entry in journal_entries if entry.mood]

    emotional_summary = "No clear emotional pattern yet."

    if moods:
        mood_counter = Counter(moods)
        dominant_mood = mood_counter.most_common(1)[0][0]

        emotional_summary = (
            f"Recent emotional trend shows {dominant_mood} state."
        )

    context["emotional_pattern"] = emotional_summary

    # ============================================================
    # 6️⃣ LAST SPIRITUAL PRINCIPLE
    # ============================================================

    last_principle = (
        SpiritualPrinciple.objects
        .filter(user=user)
        .order_by("-created_at")
        .first()
    )

    context["last_spiritual_principle"] = (
        last_principle.content if last_principle else None
    )

    return context




def generate_ai_reflection_for_user(user):
    try:
        context = build_user_reflection_context(user)

        system_prompt ="""
You are a practical spiritual mentor.

Write a short reflection (maximum 70 words).
Use simple, natural language.
Refer to the user's recent actions and emotional pattern.
Do not be poetic.
Do not exaggerate.
No metaphors.
No line breaks.
One clean paragraph only.
"""

        user_prompt = f"""
Here is the user's recent activity summary:

Movement: {context.get("movement_pattern")}
Temple Engagement: {context.get("temple_engagement")}
Event Participation: {context.get("event_participation")}
Recent Thoughts: {context.get("recent_reflections")}
Emotional Trend: {context.get("emotional_pattern")}
Last Spiritual Principle: {context.get("last_spiritual_principle")}

Generate a short reflection based on this.
"""

        response = model.generate_content([system_prompt, user_prompt])
        reflection_text = response.text.strip()
        reflection_text = reflection_text.replace("\n", " ").strip()

        return reflection_text
    
    except Exception as e:
        return "Reflection could not be generated at this time."
    


def generate_ai_prompt_for_user(user):
    """
    Generates a short reflective writing prompt
    based on recent journal moods and themes.
    """

    try:
        # Fetch last 3 journal entries
        entries = (
            JournalEntry.objects
            .filter(user=user)
            .order_by("-created_at")[:3]
        )

        moods = [e.mood for e in entries if e.mood]
        titles = [e.title for e in entries if e.title]

        dominant_mood = None
        if moods:
            from collections import Counter
            dominant_mood = Counter(moods).most_common(1)[0][0]

        context_summary = f"""
        Recent moods: {moods}
        Recent titles: {titles}
        Dominant mood: {dominant_mood}
        """

        system_prompt = """
        You are a thoughtful mentor helping someone begin journaling.

        Generate one short reflective question (maximum 25 words).
        Keep it simple and clear.
        No explanation.
        No extra text.
        Only the question.
        """

        user_prompt = f"""
        Based on this journal summary:

        {context_summary}

        Generate one reflective question.
        """

        response = model.generate_content(
            [system_prompt, user_prompt]
        )

        prompt_text = response.text.strip()
        prompt_text = prompt_text.replace("\n", " ").strip()

        return prompt_text

    except Exception as e:
        print("Gemini Prompt Error:", e)
        return "What stood out to you today during your journey?"


