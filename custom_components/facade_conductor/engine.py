"""Entscheidungslogik von Facade Conductor, ohne Abhängigkeit von Home Assistant.

Je Raum wird aus den Eingängen eine Zielposition mit Grund berechnet. Die
Rangfolge wird von unten nach oben angewendet: Jede höhere Stufe überschreibt
oder begrenzt das Ergebnis der niedrigeren. Eine begrenzende Stufe (Schlafen,
Lüften) erscheint nur dann als Grund, wenn sie die Position wirklich ändert.

Positionen wie in Home Assistant: 0 = zu, 100 = offen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum


class Phase(str, Enum):
    DAY = "day"
    DUSK = "dusk"
    NIGHT = "night"


class Window(IntEnum):
    CLOSED = 0
    TILTED = 1
    OPEN = 2


class Reason(str, Enum):
    SCHEDULE = "schedule"
    EVENING_COOLING = "evening_cooling"
    HEAT = "heat_protection"
    SLEEP = "sleep"
    SITUATION = "situation"
    WINDOW_TILTED = "window_tilted"
    WINDOW_OPEN = "window_open"
    MANUAL = "manual"
    SAFETY = "safety"


LEVEL = {
    Reason.SAFETY: 1,
    Reason.MANUAL: 2,
    Reason.WINDOW_TILTED: 3,
    Reason.WINDOW_OPEN: 3,
    Reason.SITUATION: 4,
    Reason.SLEEP: 5,
    Reason.HEAT: 6,
    Reason.SCHEDULE: 7,
    Reason.EVENING_COOLING: 7,
}


@dataclass(frozen=True)
class Positions:
    day: int = 100
    dusk: int = 25
    night: int = 0
    tilted: int = 25
    open: int = 100
    shade: int = 70


@dataclass(frozen=True)
class RoomConfig:
    positions: Positions = field(default_factory=Positions)
    # Sonnenwinkel (Azimut), in dem die Sonne auf das Fenster scheint
    sun_azimuth: tuple[float, float] | None = None
    # Stunden, in denen Schlafen hier nicht gilt, etwa (11, 18) im Raumverbund
    sleep_pause: tuple[float, float] | None = None
    sleep_cap: int = 25
    # Ganz offen nachts und beim Schlafen nur auf den Spalt wie gekippt
    open_at_night_is_gap: bool = True


@dataclass(frozen=True)
class RoomState:
    window: Window = Window.CLOSED
    asleep: bool = False
    warm: bool = False  # Abendkühlung: Raum über der Schwelle
    hold: int | None = None  # aktive Situation „nicht verändern“
    manual: int | None = None  # Handbetrieb
    safety: int | None = None  # Sicherheit: Alarm, Rauch, Stromausfall


@dataclass(frozen=True)
class House:
    phase: Phase
    hour: float
    hot: bool = False
    sun_azimuth: float | None = None


@dataclass(frozen=True)
class Decision:
    position: int
    reason: Reason

    @property
    def level(self) -> int:
        return LEVEL[self.reason]


def in_range(value: float, start: float, end: float) -> bool:
    """Bereich mit Überlauf, etwa 300 bis 30 Grad oder 22 bis 6 Uhr."""
    if start <= end:
        return start <= value <= end
    return value >= start or value <= end


def situation_active(hour: float, start: float | None, end: float | None) -> bool:
    if start is None or end is None:
        return True
    return start <= hour < end if start <= end else hour >= start or hour < end


def decide(cfg: RoomConfig, room: RoomState, house: House, current: int) -> Decision:
    """Zielposition für einen Raum. current = Position, auf der er gerade steht."""
    p = cfg.positions
    night = house.phase is Phase.NIGHT

    pos = {Phase.DAY: p.day, Phase.DUSK: p.dusk, Phase.NIGHT: p.night}[house.phase]
    reason = Reason.SCHEDULE

    if room.warm and house.phase is Phase.DUSK:
        pos, reason = p.day, Reason.EVENING_COOLING

    if (
        house.hot
        and house.phase is Phase.DAY
        and cfg.sun_azimuth is not None
        and house.sun_azimuth is not None
        and in_range(house.sun_azimuth, *cfg.sun_azimuth)
    ):
        pos, reason = p.shade, Reason.HEAT

    paused = cfg.sleep_pause is not None and situation_active(house.hour, *cfg.sleep_pause)
    asleep = room.asleep and not paused
    if asleep:
        # abdunkeln, aber nie weiter öffnen als jetzt
        cap = min(cfg.sleep_cap, current)
        if pos > cap:
            pos, reason = cap, Reason.SLEEP

    if room.hold is not None:
        pos, reason = room.hold, Reason.SITUATION

    if room.window is Window.TILTED and pos < p.tilted:
        pos, reason = p.tilted, Reason.WINDOW_TILTED
    if room.window is Window.OPEN:
        floor = p.tilted if cfg.open_at_night_is_gap and (night or asleep) else p.open
        if pos < floor:
            pos, reason = floor, Reason.WINDOW_OPEN

    if room.manual is not None:
        pos, reason = room.manual, Reason.MANUAL

    if room.safety is not None:
        pos, reason = room.safety, Reason.SAFETY

    return Decision(pos, reason)


def still_asleep(on: bool, off_for: float | None, delay: float) -> bool:
    """Kurz aufstehen weckt den Raum nicht: aus zählt erst nach der Verzögerung als wach."""
    return on or (off_for is not None and off_for < delay)


def may_move(decision: Decision, last_auto_move: float | None, now: float, rest: float = 1200) -> bool:
    """Ruhe nach einer automatischen Fahrt. Sicherheit, Hand und Fenster wirken sofort."""
    if decision.level <= 3 or last_auto_move is None:
        return True
    return now - last_auto_move >= rest


def batch(targets: dict[str, int], current: dict[str, int], tolerance: int = 2) -> dict[int, list[str]]:
    """Gleichlauf: nur was sich ändert, gebündelt je Zielposition."""
    out: dict[int, list[str]] = {}
    for entity_id, pos in targets.items():
        now = current.get(entity_id)
        if now is None or abs(now - pos) > tolerance:
            out.setdefault(pos, []).append(entity_id)
    return out


DIRECTIONS = {"n": 0, "ne": 45, "e": 90, "se": 135, "s": 180, "sw": 225, "w": 270, "nw": 315}


def direction_range(direction: str, width: float = 45) -> tuple[float, float]:
    """Sonnenwinkel, in dem die Sonne auf ein Fenster dieser Richtung scheint."""
    center = DIRECTIONS[direction]
    return ((center - width) % 360, (center + width) % 360)


def phase_for(hour: float, night_start: float, night_end: float, dark: bool) -> Phase:
    """Nachtschließung nach Uhrzeit. Dunkel am Morgen bleibt Nacht, dunkel am Abend ist Dämmerung."""
    if situation_active(hour, night_start, night_end):
        return Phase.NIGHT
    if dark:
        return Phase.NIGHT if hour < 12 else Phase.DUSK
    return Phase.DAY


class CommandLog:
    """Merkt sich eigene Befehle, damit fremde Bewegungen als Handbetrieb erkannt werden."""

    def __init__(self, grace: float = 120) -> None:
        self.grace = grace
        self._sent: dict[str, float] = {}
        self._target: dict[str, int] = {}

    def sent(self, entity_id: str, now: float, target: int | None = None) -> None:
        self._sent[entity_id] = now
        if target is not None:
            self._target[entity_id] = target

    def in_flight(self, entity_id: str, target: int, now: float) -> bool:
        """Dasselbe Ziel wurde gerade geschickt, der Rollladen fährt noch: nicht erneut senden."""
        last = self._sent.get(entity_id)
        return last is not None and now - last < self.grace and self._target.get(entity_id) == target

    def is_manual(self, entity_id: str, old: int | None, new: int | None, now: float) -> bool:
        if old is None or new is None or abs(new - old) <= 2:
            return False
        last = self._sent.get(entity_id)
        return last is None or now - last >= self.grace


class Hysteresis:
    """Zwei Schwellen gegen Hin und Her: dunkel unter low, wieder hell erst über high."""

    def __init__(self, low: float, high: float, dark: bool = False) -> None:
        self.low, self.high, self.dark = low, high, dark

    def update(self, value: float) -> bool:
        if self.dark and value > self.high:
            self.dark = False
        elif not self.dark and value < self.low:
            self.dark = True
        return self.dark
