from dataclasses import dataclass, field
from .config import Settings

TITLES = {
    "phone": "Телефон в кадре", "multiple": "Несколько людей",
    "absence": "Человек отсутствует", "head": "Поворот головы",
    "window": "Переключение окна", "camera": "Камера недоступна",
    "system": "Ошибка мониторинга",
    "alt_tab": "Alt+Tab", "copy": "Копирование · Ctrl+C",
    "paste": "Вставка · Ctrl+V", "screenshot": "Print Screen",
}
WEIGHTS = {"phone": 20, "multiple": 15, "absence": 10, "head": 5, "window": 10,
           "alt_tab": 5, "copy": 5, "paste": 5, "screenshot": 10, "camera": 0, "system": 0}


@dataclass
class Observation:
    people: int | None = None
    phones: int = 0
    faces: int = 0
    yaw: float | None = None
    window_away: bool | None = None
    camera_ok: bool = True
    boxes: list = field(default_factory=list)
    inference_ms: float = 0.0


@dataclass
class Event:
    kind: str
    start: float
    end: float | None = None
    detail: str = ""
    id: int | None = None
    evidence: str | None = None

    @property
    def duration(self):
        return max(0.0, (self.end if self.end is not None else self.start) - self.start)


class EventEngine:
    """One event per continuous episode, after a sustained observation threshold.

    Times are monotonic offsets from session start. Unknown camera observations
    never produce absence or head events. A stale frame closes vision episodes.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.pending = {}
        self.active: dict[str, Event] = {}
        self.last_time = 0.0
        self._previous_time = 0.0

    def update(self, observation: Observation, now: float):
        if now < self.last_time:
            raise ValueError("Observation time must be monotonic")
        gap = now - self.last_time > 2.0
        self.last_time = now
        s = self.settings
        visible = observation.camera_ok and observation.people is not None
        states = {
            "phone": visible and observation.phones > 0,
            "multiple": visible and (observation.people >= 2 or observation.faces >= 2),
            "absence": visible and observation.people == 0 and observation.faces == 0,
            "head": visible and observation.yaw is not None and abs(observation.yaw) >= s.head_angle,
            "window": observation.window_away is True,
            "camera": not observation.camera_ok,
        }
        thresholds = {"phone": s.phone_seconds, "multiple": s.multiple_seconds,
                      "absence": s.absence_seconds, "head": s.head_seconds,
                      "window": s.window_seconds, "camera": 0.0}
        opened, closed = [], []
        for kind, on in states.items():
            if gap and kind in ("phone", "multiple", "absence", "head"):
                self.pending.pop(kind, None)
                if kind in self.active:
                    event = self.active.pop(kind)
                    event.end = max(event.start, self._previous_time)
                    closed.append(event)
            if not on:
                self.pending.pop(kind, None)
                if kind in self.active:
                    event = self.active.pop(kind)
                    event.end = now
                    closed.append(event)
                continue
            self.pending.setdefault(kind, now)
            if kind not in self.active and now - self.pending[kind] >= thresholds[kind]:
                details = {"phone": f"Телефонов: {observation.phones}",
                           "multiple": f"Людей: {observation.people}; лиц: {observation.faces}",
                           "head": f"Угол головы: {observation.yaw or 0:.0f}°",
                           "window": "Выход из закреплённого окна экзамена",
                           "absence": "В кадре не обнаружен человек",
                           "camera": "Нет доступного кадра; визуальный анализ приостановлен"}
                event = Event(kind, self.pending[kind], detail=details[kind])
                self.active[kind] = event
                opened.append(event)
        self._previous_time = now
        return opened, closed

    def finish(self, now: float):
        events = list(self.active.values())
        for event in events:
            event.end = max(event.start, now)
        self.active.clear()
        self.pending.clear()
        return events


def risk_score(events) -> int:
    """Transparent review priority, not a probability of cheating."""
    return min(100, sum(WEIGHTS.get(e.kind if isinstance(e, Event) else e["kind"], 0) for e in events))
