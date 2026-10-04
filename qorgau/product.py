"""Presentation data derived from saved sessions, never invented demo statistics."""
from collections import Counter
from dataclasses import replace
from .config import Settings

CATEGORIES = {
    "vision": {"phone", "multiple", "absence", "head"},
    "keyboard": {"copy", "paste", "alt_tab", "screenshot"},
    "window": {"window"}, "technical": {"camera", "system"},
}
PRESETS = {
    "balanced": ("Сбалансированный", {"phone_seconds": 1.5, "multiple_seconds": 2, "absence_seconds": 5, "head_seconds": 3, "head_angle": 30, "window_seconds": 0}),
    "tolerant": ("Меньше коротких сигналов", {"phone_seconds": 2.5, "multiple_seconds": 3, "absence_seconds": 8, "head_seconds": 5, "head_angle": 40, "window_seconds": 1}),
    "responsive": ("Быстрая реакция", {"phone_seconds": 0.5, "multiple_seconds": 0.5, "absence_seconds": 3, "head_seconds": 1.5, "head_angle": 25, "window_seconds": 0}),
}


def preset_settings(settings: Settings, preset: str):
    result = replace(settings, **PRESETS[preset][1])
    result.validate()
    return result


def event_matches(event, category="all", query=""):
    kind = event.kind if hasattr(event, "kind") else event["kind"]
    detail = event.detail if hasattr(event, "detail") else event["detail"]
    from .engine import TITLES
    return (category == "all" or kind in CATEGORIES.get(category, set())) and query.strip().casefold() in f"{TITLES.get(kind, kind)} {detail}".casefold()


def overview_stats(sessions):
    # Demo sessions are explicitly separate from real exam results.
    live = [s for s in sessions if s["mode"] == "live"]
    return {"live": len(live), "demo": sum(s["mode"] == "demo" for s in sessions),
            "completed": sum(s["status"] == "completed" for s in live),
            "events": sum(s["event_count"] for s in live),
            "duration": sum(s["duration"] for s in live)}


def review_stats(events):
    counts = Counter(e["review"] for e in events)
    return {key: counts[key] for key in ("pending", "confirmed", "dismissed")}
