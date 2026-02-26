"""
Formatting helpers for user-facing responses.

Provides utilities to turn structured outputs (like Itinerary models)
into human-friendly, emoji-enhanced strings.
"""
from typing import Dict, Any, List


def _format_day(day: Dict[str, Any]) -> str:
    parts: List[str] = []
    day_title = day.get('title') or f"Day {day.get('day', '?')}"
    parts.append(f"**{day_title}**")

    schedule = day.get('schedule') or []
    for slot in schedule:
        time = slot.get('time', 'Anytime')
        activity = slot.get('activity', '')
        parts.append(f"- {time} — {activity}")

    if day.get('meals'):
        meals = day['meals']
        meal_parts = ", ".join([f"{k}: {v}" for k, v in meals.items()])
        parts.append(f"Meals: {meal_parts}")

    if day.get('notes'):
        parts.append(f"Notes: {day.get('notes')}")

    return "\n".join(parts)


def beautify_itinerary(it: Dict[str, Any]) -> str:
    """Create a friendly, emoji-rich string from itinerary dict.

    The returned string is safe for plain-text consoles and Markdown viewers.
    """
    lines: List[str] = []

    dest = it.get('destination', 'Your Destination')
    duration = it.get('duration', '?')
    total_cost = it.get('total_estimated_cost') or it.get('total_cost') or 'TBD'

    lines.append(f"🧭 *Relaxing {duration}-day trip to {dest}*")
    lines.append(f"💰 Estimated cost: {total_cost}")

    # Important notes / warnings
    notes = it.get('important_notes') or []
    if notes:
        lines.append("\n⚠️ Important:")
        for n in notes:
            lines.append(f"- {n}")

    # Days
    days = it.get('days') or []
    if days:
        lines.append("\n📅 Day-by-day plan:")
        for d in days:
            lines.append("")
            lines.append(_format_day(d))

    # Packing list
    packing = it.get('packing_list') or []
    if packing:
        lines.append("\n🎒 Packing list:")
        for item in packing:
            lines.append(f"- {item}")

    # Emergency contacts
    contacts = it.get('emergency_contacts') or {}
    if contacts:
        lines.append("\n📞 Emergency contacts:")
        for k, v in contacts.items():
            lines.append(f"- {k}: {v}")

    lines.append("\nIf you want this exported as JSON or PDF, tell me and I can prepare it.")

    return "\n".join(lines)
