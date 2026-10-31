"""Der Taktgeber: liest Sensoren, fragt die Entscheidungslogik und fährt gebündelt."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    BUNDLE_SECONDS,
    CONF_ADVANCED,
    CONF_AREA,
    CONF_COOLING_ABOVE,
    CONF_COOLING_SENSOR,
    CONF_COVERS,
    CONF_DIRECTION,
    CONF_DIRECTION_DEG,
    CONF_HOT_TEMPERATURE,
    CONF_LUX_BRIGHT,
    CONF_LUX_DARK,
    CONF_LUX_SENSOR,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_POSITIONS,
    CONF_REST_MINUTES,
    CONF_SAFETY,
    CONF_SLEEP_PAUSE_END,
    CONF_SLEEP_PAUSE_START,
    CONF_SLEEP_SENSOR,
    CONF_SLEEP_WAKE_MINUTES,
    CONF_SITUATIONS,
    CONF_SLEEP_WATTS,
    CONF_WAKE_LEAD,
    CONF_WAKE_SENSOR,
    CONF_WAKE_WAIT,
    CONF_WEATHER,
    CONF_WINDOW_MEANS,
    CONF_WINDOW_SENSOR,
    DEFAULT_POSITIONS,
    DEFAULTS,
    DEFAULT_COOLING_ABOVE,
    DEFAULT_SLEEP_WATTS,
    EVALUATE_INTERVAL_SECONDS,
    FORECAST_INTERVAL_MINUTES,
    MODE_AUTO,
    MODE_DRY_RUN,
    MODE_OFF,
    SUBENTRY_ROOM,
)
from .engine import (
    CommandLog,
    Decision,
    House,
    Hysteresis,
    Phase,
    Positions,
    RoomConfig,
    RoomState,
    Window,
    at_least,
    batch,
    curtain_position,
    decide,
    direction_range,
    may_move,
    phase_for,
    safety_position,
    situation_hold,
    sleep_on,
    still_asleep,
    wake_phase,
    wake_until,
)
from .leave import LeaveWatcher
from .messages import Messages

_LOGGER = logging.getLogger(__name__)
SUN = "sun.sun"


def _hours(value: str | None) -> float | None:
    if not value:
        return None
    h, m, *_ = (int(x) for x in value.split(":"))
    return h + m / 60


@dataclass
class Room:
    subentry_id: str
    name: str
    area: str | None
    cfg: RoomConfig
    covers: list[str]
    window_sensor: str | None
    window_means: Window
    sleep_sensor: str | None
    wake_delay: float = 0
    sleep_watts: float | None = None  # gesetzt, wenn der Schlaf-Geber ein Leistungssensor ist
    last_asleep: float | None = None
    situations: list[dict[str, Any]] = field(default_factory=list)
    situation: str | None = None  # aktive Situation
    held: int | None = None  # Position beim Beginn der Situation
    cooling_sensor: str | None = None
    cooling_above: float = DEFAULT_COOLING_ABOVE
    wake_sensor: str | None = None
    wake_lead: float = 0
    wake_wait: bool = False  # im Dunkeln erst bei Helligkeit öffnen
    woken_until: float | None = None
    decision: Decision | None = None
    state: RoomState | None = None
    manual: int | None = None
    last_auto_move: float | None = None


class Conductor:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        house = {**DEFAULTS, **entry.data, **entry.options}
        self.house = house
        self.mode = MODE_DRY_RUN
        self.phase: Phase | None = None
        self._defaults = {**DEFAULT_POSITIONS, **house.get(CONF_POSITIONS, {})}
        self._night = (_hours(house[CONF_NIGHT_START]), _hours(house[CONF_NIGHT_END]))
        self._lux = Hysteresis(house[CONF_LUX_DARK], house[CONF_LUX_BRIGHT])
        self._hot = False
        self._log = CommandLog()
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._pending: CALLBACK_TYPE | None = None
        self.safety = list(house[CONF_SAFETY])
        self.leave = LeaveWatcher(hass, house, lambda: self.mode != MODE_OFF)
        self.messages = Messages(hass, house, lambda: self.leave.persons, self._resume)
        self.rooms = [
            self._room(sub.subentry_id, sub.title, dict(sub.data))
            for sub in entry.subentries.values()
            if sub.subentry_type == SUBENTRY_ROOM
        ]

    def _room(self, subentry_id: str, name: str, data: dict[str, Any]) -> Room:
        overrides = {k: v for k, v in data.get(CONF_POSITIONS, {}).items() if v is not None}
        pos = {k: int(v) for k, v in {**self._defaults, **overrides}.items()}
        adv = data.get(CONF_ADVANCED, {})
        pause = (_hours(adv.get(CONF_SLEEP_PAUSE_START)), _hours(adv.get(CONF_SLEEP_PAUSE_END)))
        direction = data.get(CONF_DIRECTION, "none")
        cfg = RoomConfig(
            positions=Positions(**pos),
            sun_azimuth=direction_range(data[CONF_DIRECTION_DEG])
            if data.get(CONF_DIRECTION_DEG) is not None
            else None if direction == "none" else direction_range(direction),
            sleep_pause=pause if None not in pause else None,
        )
        return Room(
            subentry_id=subentry_id,
            name=name,
            area=data.get(CONF_AREA),
            cfg=cfg,
            covers=list(data[CONF_COVERS]),
            window_sensor=data.get(CONF_WINDOW_SENSOR),
            window_means=Window.OPEN if data.get(CONF_WINDOW_MEANS) == "open" else Window.TILTED,
            sleep_sensor=data.get(CONF_SLEEP_SENSOR),
            situations=list(data.get(CONF_SITUATIONS) or []),
            cooling_sensor=data.get(CONF_COOLING_SENSOR),
            wake_sensor=data.get(CONF_WAKE_SENSOR),
            wake_lead=float(data.get(CONF_WAKE_LEAD) or 0) * 60,
            wake_wait=bool(data.get(CONF_WAKE_WAIT)),
            cooling_above=float(data.get(CONF_COOLING_ABOVE) or DEFAULT_COOLING_ABOVE),
            wake_delay=float(data.get(CONF_SLEEP_WAKE_MINUTES) or 0) * 60,
            sleep_watts=float(data.get(CONF_SLEEP_WATTS) or DEFAULT_SLEEP_WATTS)
            if (data.get(CONF_SLEEP_SENSOR) or "").startswith("sensor.")
            else None,
        )

    # Lebenszyklus

    async def async_start(self) -> None:
        # Personen zählen für „jemand zu Hause“ bei der Sicherheit
        watched = [SUN, *(t["entity"] for t in self.safety), *(self.leave.persons if self.safety else [])]
        if lux := self.house.get(CONF_LUX_SENSOR):
            watched.append(lux)
        for room in self.rooms:
            watched += room.covers
            watched += [e for e in (room.window_sensor, room.sleep_sensor, room.cooling_sensor, room.wake_sensor) if e]
            watched += [s["entity"] for s in room.situations]
        self._unsubs.append(async_track_state_change_event(self.hass, watched, self._on_state))
        self._unsubs.append(
            async_track_time_interval(self.hass, self._on_tick, timedelta(seconds=EVALUATE_INTERVAL_SECONDS))
        )
        self._unsubs.append(
            async_track_time_interval(self.hass, self._refresh_forecast, timedelta(minutes=FORECAST_INTERVAL_MINUTES))
        )
        await self.leave.async_start()
        self.messages.async_start()
        await self._refresh_forecast()
        await self.async_evaluate()

    @callback
    def async_stop(self) -> None:
        self.leave.async_stop()
        self.messages.async_stop()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._pending:
            self._pending()
            self._pending = None

    @callback
    def add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if mode != MODE_AUTO:
            for room in self.rooms:
                room.manual = None
        self._schedule()

    @callback
    def set_manual(self, room: Room, on: bool) -> None:
        """Handbetrieb von außen: an hält die jetzige Position, aus gibt den Raum der Automatik zurück."""
        if on:
            positions = self._current(room)
            room.manual = round(sum(positions.values()) / len(positions)) if positions else None
        else:
            room.manual = None
        self._schedule()

    @callback
    def _resume(self, subentry_id: str) -> None:
        for room in self.rooms:
            if room.subentry_id == subentry_id:
                self.set_manual(room, False)

    async def async_command(self, rooms: list[Room], position: int) -> None:
        """Fahrbefehl über eine Gruppe. In der Automatik gehen die Räume in Handbetrieb und fahren im Takt,
        sonst fährt der Befehl direkt, weil FaCo dann selbst nichts bewegt."""
        if self.mode == MODE_AUTO:
            for room in rooms:
                room.manual = position
            self._schedule()
            return
        covers = [c for room in rooms for c in room.covers]
        if covers:
            await self.hass.services.async_call(
                "cover", "set_cover_position", {"position": position}, target={"entity_id": covers}, blocking=False
            )

    # Eingänge

    @callback
    def _on_state(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        # Im Probelauf fährt FaCo nie selbst, jede Fahrt käme von alten Automationen und wäre kein Handbetrieb
        if entity_id.startswith("cover.") and self.mode == MODE_AUTO:
            old, new = event.data["old_state"], event.data["new_state"]
            if self._log.is_manual(entity_id, _position(old), _position(new), time.monotonic()):
                for room in self.rooms:
                    if entity_id in room.covers:
                        if room.manual is None:
                            self.hass.async_create_task(self.messages.async_manual(room))
                        room.manual = _position(new)
        self._schedule()

    @callback
    def _schedule(self) -> None:
        """Ereignisse kurz sammeln, damit gleichzeitige Änderungen eine Entscheidung ergeben."""
        if self._pending is None:
            self._pending = async_call_later(self.hass, BUNDLE_SECONDS, self._on_tick)

    async def _on_tick(self, _now: Any = None) -> None:
        self._pending = None
        await self.async_evaluate()

    async def _refresh_forecast(self, _now: Any = None) -> None:
        weather = self.house.get(CONF_WEATHER)
        if not weather:
            self._hot = False
            return
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"type": "daily"},
                target={"entity_id": weather},
                blocking=True,
                return_response=True,
            )
            high = response[weather]["forecast"][0]["temperature"]
            self._hot = float(high) > float(self.house[CONF_HOT_TEMPERATURE])
        except Exception:  # noqa: BLE001 - ohne Prognose kein Hitzeschutz, aber weiterlaufen
            _LOGGER.warning("Wetterprognose von %s nicht lesbar, Hitzeschutz ruht", weather)
            self._hot = False

    def _dark(self) -> bool:
        if lux := self.house.get(CONF_LUX_SENSOR):
            state = self.hass.states.get(lux)
            try:
                return self._lux.update(float(state.state))
            except (AttributeError, ValueError):
                pass  # Sensor fehlt: Sonnenstand nehmen
        sun = self.hass.states.get(SUN)
        return sun is not None and sun.state == "below_horizon"

    def _window(self, room: Room) -> Window:
        if not room.window_sensor:
            return Window.CLOSED
        state = self.hass.states.get(room.window_sensor)
        return room.window_means if state and state.state == STATE_ON else Window.CLOSED

    def _asleep(self, room: Room) -> bool:
        state = self.hass.states.get(room.sleep_sensor) if room.sleep_sensor else None
        on = sleep_on(state.state if state else None, room.sleep_watts)
        # Aufstehpause selbst mitzählen: ein Leistungssensor ändert seinen Wert ständig,
        # sein last_changed sagt nichts darüber, seit wann niemand mehr schläft
        now = time.monotonic()
        if on:
            room.last_asleep = now
        off_for = None if on or room.last_asleep is None else now - room.last_asleep
        return still_asleep(on, off_for, room.wake_delay)

    def _alarm(self, entity_id: str | None) -> float | None:
        """Weckzeit als Zeitstempel: Handy-Sensor mit Datum oder Datum-Zeit-Helfer, auch nur mit Uhrzeit."""
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None:
            return None
        value = dt_util.parse_datetime(state.state)
        if value is None and (clock := dt_util.parse_time(state.state)):
            value = dt_util.now().replace(hour=clock.hour, minute=clock.minute, second=clock.second, microsecond=0)
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())
        return value.timestamp()

    def _curtain(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.attributes.get("device_class") == "curtain"

    def _warm(self, room: Room) -> bool:
        state = self.hass.states.get(room.cooling_sensor) if room.cooling_sensor else None
        return at_least(state.state if state else None, room.cooling_above)

    def _current(self, room: Room) -> dict[str, int]:
        return {c: p for c in room.covers if (p := _position(self.hass.states.get(c))) is not None}

    # Entscheidung

    async def async_evaluate(self) -> None:
        now = dt_util.now()
        hour = now.hour + now.minute / 60
        dark = self._dark()
        phase = phase_for(hour, *self._night, dark=dark)
        if phase != self.phase:
            # neue Tagesphase beendet den Handbetrieb
            for room in self.rooms:
                room.manual = None
            self.phase = phase
        sun = self.hass.states.get(SUN)
        azimuth = sun.attributes.get("azimuth") if sun else None
        house = House(phase, hour, hot=self._hot, sun_azimuth=azimuth)

        states = {t["entity"]: (st.state if (st := self.hass.states.get(t["entity"])) else None) for t in self.safety}
        safety = safety_position(self.safety, states, self.leave.anyone_home())
        stamp = time.monotonic()
        targets: dict[str, int] = {}
        current: dict[str, int] = {}
        moving: list[Room] = []
        for room in self.rooms:
            noon = now.replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
            end = noon if now.timestamp() < noon else now.timestamp() + 3600
            room.woken_until = wake_until(
                self._alarm(room.wake_sensor), now.timestamp(), room.woken_until, room.wake_lead, end
            )
            room.state = RoomState(
                window=self._window(room),
                asleep=self._asleep(room) and room.woken_until is None,
                warm=self._warm(room),
                manual=room.manual,
                safety=safety,
            )
            positions = self._current(room)
            if not positions:
                room.decision = None
                continue
            # Vorhänge innen verfälschen die Stellung des Raums nicht, wenn es auch Rollläden gibt
            outside = {c: p for c, p in positions.items() if not self._curtain(c)} or positions
            here = round(sum(outside.values()) / len(outside))
            states = {s["entity"]: (st.state if (st := self.hass.states.get(s["entity"])) else None) for s in room.situations}
            room.situation, room.held, hold = situation_hold(room.situations, states, here, room.situation, room.held)
            room.state = replace(room.state, hold=hold)
            room_house = house
            if room.woken_until is not None:
                room_house = replace(house, phase=wake_phase(phase, dark, room.wake_wait))
            room.decision = decide(room.cfg, room.state, room_house, here)
            current.update(positions)
            if self.mode == MODE_AUTO and may_move(room.decision, room.last_auto_move, stamp, self._rest()):
                room_phase = room_house.phase
                targets.update(
                    {
                        c: curtain_position(room.decision, room_phase) if self._curtain(c) else room.decision.position
                        for c in positions
                    }
                )
                moving.append(room)

        if self.mode == MODE_AUTO and targets:
            targets = {e: p for e, p in targets.items() if not self._log.in_flight(e, p, stamp)}
            plan = batch(targets, current)
            for position, entity_ids in plan.items():
                for entity_id in entity_ids:
                    self._log.sent(entity_id, stamp, position)
                await self.hass.services.async_call(
                    "cover",
                    "set_cover_position",
                    {"position": position},
                    target={"entity_id": entity_ids},
                    blocking=False,
                )
            sent = {e for ids in plan.values() for e in ids}
            for room in moving:
                if sent.intersection(room.covers):
                    room.last_auto_move = stamp

        if self.mode != MODE_OFF:
            await self.messages.async_check(self.rooms, stamp)
        for update in list(self._listeners):
            update()

    def _rest(self) -> float:
        return float(self.house[CONF_REST_MINUTES]) * 60


def _position(state: Any) -> int | None:
    if state is None:
        return None
    value = state.attributes.get("current_position")
    if value is None:
        return {"open": 100, "closed": 0}.get(state.state)
    return int(value)
