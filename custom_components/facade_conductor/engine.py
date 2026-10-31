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
    FROST = "frost"
    SAFETY = "safety"


LEVEL = {
    Reason.SAFETY: 1,
    Reason.FROST: 1,
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
    frost: bool = False  # Frostschutz: nicht fahren, damit nichts festfriert


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

    # Situation hält oder fährt, aber nachts gilt die Nachtschließung, und Hitze oder Schlafen dunkeln weiter ab
    if room.hold is not None and not night and (room.hold < pos or reason not in (Reason.HEAT, Reason.SLEEP)):
        pos, reason = room.hold, Reason.SITUATION

    if room.window is Window.TILTED and pos < p.tilted:
        pos, reason = p.tilted, Reason.WINDOW_TILTED
    if room.window is Window.OPEN:
        floor = p.tilted if cfg.open_at_night_is_gap and (night or asleep) else p.open
        if pos < floor:
            pos, reason = floor, Reason.WINDOW_OPEN

    if room.manual is not None:
        pos, reason = room.manual, Reason.MANUAL

    # schützt das Gerät, deshalb über dem Handbetrieb, aber unter der Sicherheit der Menschen
    if room.frost:
        pos, reason = current, Reason.FROST

    if room.safety is not None:
        pos, reason = room.safety, Reason.SAFETY

    return Decision(pos, reason)


def sleep_on(state: str | None, watts: float | None) -> bool:
    """Zeigt der Schlaf-Geber Schlafen an? Schalter und Sensoren mit „on“, Leistung über der Schwelle."""
    return state == "on" if watts is None else at_least(state, watts)


def warm_step(
    inside: str | None, threshold: float, was_warm: bool, outside: str | None = None, need_cooler: bool = False
) -> bool:
    """Abendkühlung: warm ab der Schwelle, wieder kühl erst 0,5 °C darunter, damit die Grenze nicht flattert.

    Auf Wunsch nur, wenn es draußen kühler ist als drinnen; ohne Außenwert dann nicht.
    """
    try:
        t = float(inside)
    except (TypeError, ValueError):
        return False
    warm = t >= threshold or (was_warm and t >= threshold - 0.5)
    if warm and need_cooler:
        try:
            return float(outside) < t
        except (TypeError, ValueError):
            return False
    return warm


FROST_RAIN_WITHIN = 12 * 3600


def raining(state: str | None) -> bool:
    """Regensensor: ein Schalter mit „on“ oder eine Regenmenge über 0."""
    return state == "on" or at_least(state, 0.01)


def frost_step(active: bool, temperature: str | None, last_rain: float | None, now: float) -> bool:
    """Frostschutz: nach Regen bei 0 °C oder kälter nicht fahren, damit nichts festfriert und reißt.

    Gilt, wenn es in den letzten 12 Stunden geregnet hat, und hält, bis es über 1 °C warm ist.
    """
    try:
        t = float(temperature)
    except (TypeError, ValueError):
        return False
    if active:
        return t <= 1
    return t <= 0 and last_rain is not None and now - last_rain <= FROST_RAIN_WITHIN


def at_least(state: str | None, threshold: float) -> bool:
    """Messwert mindestens so hoch wie die Schwelle; nicht verfügbar zählt als nein."""
    try:
        return float(state) >= threshold
    except (TypeError, ValueError):
        return False


def away(person_state: str | None) -> bool:
    """Ist die Person sicher unterwegs? Unbekannt zählt als zu Hause, damit kein Wecker verloren geht."""
    return person_state not in (None, "home", "unknown", "unavailable")


ANNOUNCE_REPEAT = 1800


def may_announce(key: str, now: float, last: dict[str, float], quiet: bool) -> bool:
    """Durchsage nicht nachts und nicht, solange jemand schläft; dieselbe höchstens alle 30 Minuten."""
    if quiet or now - last.get(key, float("-inf")) < ANNOUNCE_REPEAT:
        return False
    last[key] = now
    return True


def wake_until(alarm: float | None, now: float, until: float | None, lead: float, end: float) -> float | None:
    """Wecker: ab Weckzeit minus Vorlauf gilt der Raum als wach, und zwar bis `end`.

    Das Ende wird gemerkt, weil das Handy nach dem Klingeln schon die nächste Weckzeit meldet.
    Eine Stunde nach der Weckzeit greift er nicht mehr neu, etwa nach einem Neustart.
    """
    if until is not None and now < until:
        return until
    if alarm is not None and alarm - lead <= now < alarm + 3600:
        return end
    return None


def wake_phase(phase: Phase, dark: bool, wait_for_light: bool) -> Phase:
    """Phase eines geweckten Raums: die Nacht endet, im Dunkeln mit Spalt oder erst bei Helligkeit."""
    if phase is not Phase.NIGHT:
        return phase
    if dark:
        return Phase.NIGHT if wait_for_light else Phase.DUSK
    return Phase.DAY


def safety_trigger(triggers: list[dict], states: dict[str, str | None], anyone_home: bool) -> tuple[str, int] | None:
    """Erster aktiver Sicherheits-Auslöser mit einer Position für „jemand zu Hause“ oder „Haus leer“.

    Eine leere Position heißt: dieser Auslöser tut in dieser Lage nichts.
    """
    for trigger in triggers:
        if states.get(trigger["entity"]) in trigger["states"]:
            position = trigger.get("home" if anyone_home else "away")
            if position is not None:
                return trigger["entity"], position
    return None


def safety_position(triggers: list[dict], states: dict[str, str | None], anyone_home: bool) -> int | None:
    found = safety_trigger(triggers, states, anyone_home)
    return found[1] if found else None


def situation_hold(
    situations: list[dict], states: dict[str, str | None], current: int, active_before: str | None, held_before: int | None
) -> tuple[str | None, int | None, int | None]:
    """Erste aktive Situation eines Raums: (Entität, gemerkte Position, Halteposition).

    Ohne feste Position hält die Situation die Stellung, die der Raum bei ihrem Beginn hatte.
    """
    active = next((s for s in situations if states.get(s["entity"]) in s["states"]), None)
    if active is None:
        return None, None, None
    entity = active["entity"]
    held = held_before if entity == active_before else current
    position = active.get("position")
    return entity, held, held if position is None else position


def still_asleep(on: bool, off_for: float | None, delay: float) -> bool:
    """Kurz aufstehen weckt den Raum nicht: aus zählt erst nach der Verzögerung als wach."""
    return on or (off_for is not None and off_for < delay)


# Beim Verlassen: erst warten, ob die Person wirklich weg ist (springendes GPS), dann melden
LEAVE_WARN_AFTER = 120
LEAVE_FORWARD_AFTER = 420
LEAVE_WAITING, LEAVE_WARNED, LEAVE_FORWARDED, LEAVE_DONE = range(4)


def leave_step(
    stage: int, since: float, now: float, anyone_home: bool, doors_open: bool, windows_open: bool
) -> tuple[int, str | None]:
    """Nächster Schritt der Warnung beim Verlassen: neue Stufe und was zu tun ist.

    Erledigt, sobald jemand heimkommt oder alles zu ist. Nach 2 Minuten bekommt die gehende Person
    eine Meldung, nach 7 Minuten ohne Antwort die anderen, aber nur bei offenen Türen.
    """
    if stage == LEAVE_DONE or anyone_home or not (doors_open or windows_open):
        return LEAVE_DONE, None
    elapsed = now - since
    if stage == LEAVE_WAITING and elapsed >= LEAVE_WARN_AFTER:
        return LEAVE_WARNED, "warn_person"
    if stage == LEAVE_WARNED and elapsed >= LEAVE_FORWARD_AFTER and doors_open:
        return LEAVE_FORWARDED, "warn_others"
    return stage, None


UNREACHABLE_AFTER = 900


def due_unreachable(down_since: dict[str, float], sent: set[str], unavailable: set[str], now: float) -> list[str]:
    """Rollläden, die gerade 15 Minuten nicht erreichbar sind und noch nicht gemeldet wurden.

    Merkt sich Beginn und Meldung je Rollladen; kommt er zurück, wird beides vergessen.
    """
    for cover in list(down_since):
        if cover not in unavailable:
            down_since.pop(cover)
            sent.discard(cover)
    due = []
    for cover in unavailable:
        since = down_since.setdefault(cover, now)
        if now - since >= UNREACHABLE_AFTER and cover not in sent:
            sent.add(cover)
            due.append(cover)
    return due


def curtain_position(decision: Decision, phase: Phase) -> int:
    """Vorhang innen: tagsüber offen, sonst zu als Sichtschutz, beim Schlafen dunkel.

    Hand, Sicherheit und Situationen gelten wie beim Rollladen. Hitzeschutz wirkt innen kaum,
    und ein offenes Fenster braucht keinen Spalt im Vorhang.
    """
    if decision.reason in (Reason.MANUAL, Reason.SAFETY, Reason.SITUATION):
        return decision.position
    if decision.reason is Reason.SLEEP:
        return 0
    return 100 if phase is Phase.DAY else 0


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


def direction_range(direction: str | float, width: float = 45) -> tuple[float, float]:
    """Sonnenwinkel, in dem die Sonne auf ein Fenster dieser Richtung scheint: Name oder Gradzahl."""
    center = DIRECTIONS[direction] if isinstance(direction, str) else float(direction)
    return ((center - width) % 360, (center + width) % 360)


def phase_for(hour: float, night_start: float, night_end: float, dark: bool) -> Phase:
    """Nachtschließung nach Uhrzeit. Außerhalb davon heißt dunkel Dämmerung, morgens wie abends."""
    if situation_active(hour, night_start, night_end):
        return Phase.NIGHT
    if dark:
        return Phase.DUSK
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


class LuxFilter:
    """Helligkeit wie ein Mensch sie sieht: Mittel über 10 Minuten statt Momentwert, zwei Schwellen, und ein
    Wechsel muss einige Minuten gelten. Schwankt das Licht stark, wie bei Aprilwetter, doppelt so lange.
    """

    def __init__(self, low: float, high: float, window: float = 600, hold: float = 300) -> None:
        self.low, self.high, self.window, self.hold = low, high, window, hold
        self.dark: bool | None = None
        self._samples: list[tuple[float, float]] = []
        self._since: float | None = None

    def update(self, value: float, now: float) -> bool:
        self._samples = [(t, v) for t, v in self._samples if now - t < self.window] + [(now, value)]
        values = [v for _, v in self._samples]
        mean = sum(values) / len(values)
        if self.dark is None:
            # nach dem Start gleich richtig liegen, nicht erst nach der Wartezeit
            self.dark = value < (self.low + self.high) / 2
            return self.dark
        wants = mean <= self.high if self.dark else mean < self.low
        if wants == self.dark:
            self._since = None
            return self.dark
        if self._since is None:
            self._since = now
        hold = self.hold * (2 if max(values) - min(values) > mean else 1)
        if now - self._since >= hold:
            self.dark, self._since = wants, None
        return self.dark


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
