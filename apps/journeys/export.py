"""Plain-text itinerary for sharing, in the plan's language."""

from apps.journeys import planner

_LABELS = {
    "en": {
        "from": "From", "dates": "Dates", "travellers": "Travellers", "day": "Day",
        "checklist": "Checklist", "bookings": "My bookings and stays", "notes": "Notes",
        "footer": "Planned with KumbhaPath. Suggestions only — confirm timings and arrangements with official announcements.",
    },
    "hi": {
        "from": "कहाँ से", "dates": "तारीखें", "travellers": "यात्री", "day": "दिन",
        "checklist": "जाँच सूची", "bookings": "मेरी बुकिंग और ठहराव", "notes": "नोट्स",
        "footer": "KumbhaPath से योजना बनाई गई। केवल सुझाव — समय और व्यवस्थाओं की पुष्टि आधिकारिक घोषणाओं से करें।",
    },
    "mr": {
        "from": "कुठून", "dates": "तारखा", "travellers": "प्रवासी", "day": "दिवस",
        "checklist": "तपासणी यादी", "bookings": "माझी आरक्षणे आणि निवास", "notes": "नोंदी",
        "footer": "KumbhaPath वापरून नियोजन केले. फक्त सूचना — वेळा आणि व्यवस्थांची खात्री अधिकृत घोषणांवरून करा.",
    },
}


def itinerary_text(plan) -> str:
    label = _LABELS.get(plan.language, _LABELS["en"])
    lines = [plan.title, ""]
    origin = ", ".join(x for x in (plan.origin_city, plan.origin_state) if x)
    if origin:
        lines.append(f"{label['from']}: {origin}")
    if plan.arrival_date and plan.departure_date:
        lines.append(f"{label['dates']}: {plan.arrival_date:%d %b %Y} – {plan.departure_date:%d %b %Y}")
    lines.append(f"{label['travellers']}: {plan.travellers}")

    for day in plan.days.all():
        lines += ["", f"{label['day']} {day.day_number}"
                  + (f" · {day.date:%a %d %b}" if day.date else "")
                  + (f" — {day.title}" if day.title else "")]
        for item in day.items.all():
            mark = "✓ " if item.is_done else "• "
            lines.append(f"  {mark}{item.title}")

    checklist = list(plan.checklist.all())
    if checklist:
        lines += ["", label["checklist"]]
        lines += [f"  [{'x' if c.is_done else ' '}] {c.text}" for c in checklist]

    references = list(plan.references.all())
    if references:
        lines += ["", label["bookings"]]
        for ref in references:
            parts = [ref.title, ref.provider, ref.booking_reference]
            lines.append("  • " + " · ".join(p for p in parts if p))

    if plan.notes.strip():
        lines += ["", f"{label['notes']}:", plan.notes.strip()]
    budget = planner.budget_plan(plan)
    if budget:
        lines += ["", f"₹ {budget['total']}"]
    lines += ["", label["footer"]]
    return "\n".join(lines)
