"""Der Taktgeber: liest Sensoren, fragt die Entscheidungslogik und fährt gebündelt."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any

from homeassistant.components.cover import CoverEntityFeature
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
    CONF_COOLING_OUTSIDE,
    CONF_COOLING_SENSOR,
    CONF_COVER_DIRECTIONS,
    CONF_COVERS,
    CONF_DIRECTION,
    CONF_DIRECTION_DEG,
    CONF_HOT_TEMPERATURE,
    CONF_LUX_BRIGHT,
    CONF_LUX_DARK,
    CONF_LUX_SENSOR,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_OUTDOOR_TEMP,
    CONF_POSITIONS,
    CONF_RAIN_LEVEL,
    CONF_RAIN_SENSOR,
    CONF_SLAT_TILT,
    CONF_VACATION_AFTER,
    CONF_WIND_DIRECTION,
    CONF_WIND_GUST,
    CONF_WIND_LIMIT,
    CONF_WIND_SPEED,
    CONF_REST_MINUTES,
    CONF_SAFETY,
    CONF_SLEEP_PAUSE_END,
    CONF_SLEEP_PAUSE_START,
    CONF_SLEEP_SENSOR,
    CONF_SLEEP_WAKE_MINUTES,
    CONF_SITUATIONS,
    CONF_SLEEP_WATTS,
    CONF_SPEAKER,
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
    DOMAIN,
    SUBENTRY_ROOM,
)
from .engine import (
    DIRECTIONS,
    CommandLog,
    Decision,
    House,
    LuxFilter,
    Phase,
    Positions,
    Reason,
    RoomConfig,
    RoomState,
    Window,
    away,
    batch,
    blind_tilt,
    curtain_position,
    decide,
    direction_range,
    may_move,
    frost_step,
    lagged_phase,
    phase_for,
    rain_at_least,
    rain_in,
    raining,
    safety_trigger,
    situation_hold,
    stand_still,
    tilt_due,
    to_kmh,
    sleep_on,
    still_asleep,
    wake_phase,
    vacation_offset,
    vacation_position,
    wake_until,
    warm_step,
    wet,
    wind_step,
)
from .leave import LeaveWatcher, owner
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
    cooling_outside: bool = False  # nur offen lassen, wenn es draußen kühler ist
    warm: bool = False
    cover_azimuth: dict[str, tuple[float, float]] = field(default_factory=dict)  # Eckzimmer
    facing: float | None = None  # Blickrichtung des Fensters in Grad, für Regen
    rain_warned: bool = False  # Regen auf offene Tür schon gemeldet
    vacation_phase: Phase | None = None
    wake_sensor: str | None = None
    wake_lead: float = 0
    wake_wait: bool = False  # im Dunkeln erst bei Helligkeit öffnen
    woken_until: float | None = None
    speaker: str | None = None  # Lautsprecher für Durchsagen
    decision: Decision | None = None
    state: RoomState | None = None
    manual: int | None = None
    manual_hold: bool = False  # von Hand bewegt: alles so lassen; über eine Gruppe: hinfahren
    wake_owner: str | None = None  # Person, zu deren Handy der Wecker gehört
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
        self._lux = LuxFilter(house[CONF_LUX_DARK], house[CONF_LUX_BRIGHT])
        self.frost = False
        # shortcut: Regen nur seit dem Start gemerkt; nach einem Neustart greift Frostschutz erst beim nächsten Regen
        self._last_rain: float | None = None
        self._safety_trigger: str | None = None
        self._last_heavy: float | None = None  # letzter Regen ab der gewählten Stufe
        self.wind = False
        self._last_strong: float | None = None
        self._tilt_sent: dict[str, int] = {}
        self.vacation_switch = False
        self.vacation = False
        self._away_since: float | None = None
        self._phase_changed = 0.0
        self._lock = asyncio.Lock()
        self._snapshot: Any = None
        self._hot = False
        self._log = CommandLog()
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._pending: CALLBACK_TYPE | None = None
        self.safety = list(house[CONF_SAFETY])
        self.leave = LeaveWatcher(hass, house, lambda: self.mode != MODE_OFF)
        self.messages = Messages(hass, house, lambda: self.leave.persons, self._resume, self._quiet)
        self.rooms = [
            self._room(sub.subentry_id, sub.title, dict(sub.data))
            for sub in entry.subentries.values()
            if sub.subentry_type == SUBENTRY_ROOM
        ]
        # Speichern im Panel lädt neu: Handbetrieb, Ruhezeit und eigene Befehle sollen das überstehen
        kept = hass.data.get(DOMAIN, {}).pop("kept", None)
        if kept:
            self._log, self._tilt_sent = kept["log"], kept["tilt"]
            for room in self.rooms:
                room.manual, room.manual_hold, room.last_auto_move = kept["rooms"].get(
                    room.subentry_id, (None, False, None)
                )

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
            cooling_outside=bool(data.get(CONF_COOLING_OUTSIDE)),
            cover_azimuth={c: direction_range(d) for c, d in (data.get(CONF_COVER_DIRECTIONS) or {}).items()},
            facing=float(data[CONF_DIRECTION_DEG])
            if data.get(CONF_DIRECTION_DEG) is not None
            else DIRECTIONS.get(direction),
            speaker=data.get(CONF_SPEAKER),
            wake_delay=float(data.get(CONF_SLEEP_WAKE_MINUTES) or 0) * 60,
            sleep_watts=float(data.get(CONF_SLEEP_WATTS) or DEFAULT_SLEEP_WATTS)
            if (data.get(CONF_SLEEP_SENSOR) or "").startswith("sensor.")
            else None,
        )

    # Lebenszyklus

    async def async_start(self) -> None:
        # Personen zählen für „jemand zu Hause“ bei der Sicherheit
        watched = [SUN, *(t["entity"] for t in self.safety), *(self.leave.persons if self.safety else [])]
        weather = (CONF_LUX_SENSOR, CONF_OUTDOOR_TEMP, CONF_RAIN_SENSOR, CONF_WIND_DIRECTION, CONF_WIND_SPEED, CONF_WIND_GUST)
        watched += [e for e in (self.house.get(k) for k in weather) if e]
        for room in self.rooms:
            watched += room.covers
            watched += [e for e in (room.window_sensor, room.sleep_sensor, room.cooling_sensor, room.wake_sensor) if e]
            watched += [s["entity"] for s in room.situations]
        # Messwerte, die sich ständig ändern, liest der Minutentakt; sie lösen keine eigene Rechnung aus
        self._slow = {e for e in (self.house.get(k) for k in weather) if e and e != self.house.get(CONF_RAIN_SENSOR)}
        self._slow |= {e for r in self.rooms for e in (r.cooling_sensor, r.sleep_sensor) if e and e.startswith("sensor.")}
        for room in self.rooms:
            room.wake_owner = owner(self.hass, room.wake_sensor) if room.wake_sensor else None
        self._unsubs.append(async_track_state_change_event(self.hass, watched, self._on_state))
        self._unsubs.append(
            async_track_time_interval(self.hass, self._on_interval, timedelta(seconds=EVALUATE_INTERVAL_SECONDS))
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
        self.hass.data.setdefault(DOMAIN, {})["kept"] = {
            "log": self._log,
            "tilt": self._tilt_sent,
            "rooms": {r.subentry_id: (r.manual, r.manual_hold, r.last_auto_move) for r in self.rooms},
        }
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
            room.manual_hold = True
        else:
            room.manual = None
        self._schedule()

    @callback
    def set_vacation(self, on: bool) -> None:
        self.vacation_switch = on
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
                room.manual, room.manual_hold = position, False
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
        if entity_id in self._slow:
            return
        # Im Probelauf fährt FaCo nie selbst, jede Fahrt käme von alten Automationen und wäre kein Handbetrieb
        if entity_id.startswith("cover.") and self.mode == MODE_AUTO:
            old, new = event.data["old_state"], event.data["new_state"]
            if self._log.is_manual(entity_id, _position(old), _position(new), time.monotonic()):
                for room in self.rooms:
                    if entity_id in room.covers:
                        if room.manual is None:
                            self._task(self.messages.async_manual(room))
                        room.manual, room.manual_hold = _position(new), True
        self._schedule()

    @callback
    def _schedule(self) -> None:
        """Ereignisse kurz sammeln, damit gleichzeitige Änderungen eine Entscheidung ergeben."""
        # vor dem Start nicht: dann fehlen beim Hochfahren noch Sensoren, ein offenes Fenster sähe zu aus
        if self._pending is None and self._unsubs:
            self._pending = async_call_later(self.hass, BUNDLE_SECONDS, self._on_tick)

    async def _on_tick(self, _now: Any = None) -> None:
        self._pending = None
        await self.async_evaluate()

    async def _on_interval(self, _now: Any = None) -> None:
        await self.async_evaluate()

    @callback
    def _task(self, coro: Any) -> None:
        """Meldungen im Hintergrund, beim Entladen mit beendet."""
        self.entry.async_create_background_task(self.hass, coro, "facade_conductor_message")

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
                return self._lux.update(float(state.state), time.monotonic())
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

    def _alarm(self, room: Room) -> float | None:
        """Weckzeit als Zeitstempel: Handy-Sensor mit Datum oder Datum-Zeit-Helfer, auch nur mit Uhrzeit."""
        state = self.hass.states.get(room.wake_sensor) if room.wake_sensor else None
        if state is None:
            return None
        # der Wecker vom Handy einer Person zählt nur, wenn sie zu Hause ist
        if room.wake_owner and away(self._value(room.wake_owner)):
            return None
        value = dt_util.parse_datetime(state.state)
        if value is None and (clock := dt_util.parse_time(state.state)):
            value = dt_util.now().replace(hour=clock.hour, minute=clock.minute, second=clock.second, microsecond=0)
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())
        return value.timestamp()

    def _quiet(self) -> bool:
        """Keine Durchsagen nachts und solange in einem Raum jemand schläft."""
        return self.phase is Phase.NIGHT or any(r.state is not None and r.state.asleep for r in self.rooms)

    def _blind(self, entity_id: str) -> bool:
        """Jalousie oder Raffstore: eigene Geräteart oder Lamellen, die sich stellen lassen."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        return state.attributes.get("device_class") == "blind" or bool(
            int(state.attributes.get("supported_features") or 0) & CoverEntityFeature.SET_TILT_POSITION
        )

    def _door(self, room: Room) -> bool:
        state = self.hass.states.get(room.window_sensor) if room.window_sensor else None
        return state is not None and state.attributes.get("device_class") in ("door", "garage_door")

    def _curtain(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.attributes.get("device_class") == "curtain"

    def _value(self, entity_id: str | None) -> str | None:
        state = self.hass.states.get(entity_id) if entity_id else None
        return state.state if state else None

    def _kmh(self, key: str) -> str | None:
        state = self.hass.states.get(self.house.get(key) or "")
        return to_kmh(state.state, state.attributes.get("unit_of_measurement")) if state else None

    def _warm(self, room: Room) -> bool:
        room.warm = warm_step(
            self._value(room.cooling_sensor),
            room.cooling_above,
            room.warm,
            self._value(self.house.get(CONF_OUTDOOR_TEMP)),
            room.cooling_outside,
        )
        return room.warm

    def _current(self, room: Room) -> dict[str, int]:
        return {c: p for c in room.covers if (p := _position(self.hass.states.get(c))) is not None}

    # Entscheidung

    async def async_evaluate(self) -> None:
        # Takt und gebündelte Ereignisse dürfen sich nicht überholen
        async with self._lock:
            await self._evaluate()

    async def _evaluate(self) -> None:
        now = dt_util.now()
        hour = now.hour + now.minute / 60
        dark = self._dark()
        phase = phase_for(hour, *self._night, dark=dark)
        if phase != self.phase:
            # neue Tagesphase beendet den Handbetrieb
            for room in self.rooms:
                room.manual = None
            self.phase = phase
            self._phase_changed = time.monotonic()
        sun = self.hass.states.get(SUN)
        azimuth = sun.attributes.get("azimuth") if sun else None
        house = House(phase, hour, hot=self._hot, sun_azimuth=azimuth)

        states = {t["entity"]: (st.state if (st := self.hass.states.get(t["entity"])) else None) for t in self.safety}
        found = safety_trigger(self.safety, states, self.leave.anyone_home())
        safety = found[1] if found else None
        stamp = time.monotonic()
        if found and found[0] != self._safety_trigger and self.mode != MODE_OFF:
            self._task(self.messages.async_safety(*found))
        self._safety_trigger = found[0] if found else None
        if raining(self._value(self.house.get(CONF_RAIN_SENSOR))):
            self._last_rain = stamp
        self.frost = frost_step(self.frost, self._value(self.house.get(CONF_OUTDOOR_TEMP)), self._last_rain, stamp)
        if rain_at_least(self._value(self.house.get(CONF_RAIN_SENSOR)), self.house[CONF_RAIN_LEVEL]):
            self._last_heavy = stamp
        wet_now = wet(self._last_heavy, stamp)
        wind_from = self._value(self.house.get(CONF_WIND_DIRECTION))
        wind_speed = self._kmh(CONF_WIND_SPEED)
        self.wind, self._last_strong = wind_step(
            self._last_strong, self._kmh(CONF_WIND_GUST), float(self.house[CONF_WIND_LIMIT]), stamp
        )
        home = self.leave.anyone_home()
        self._away_since = None if home else (self._away_since or stamp)
        after = float(self.house[CONF_VACATION_AFTER]) * 3600
        self.vacation = self.vacation_switch or bool(after and self._away_since and stamp - self._away_since >= after)
        tilts: dict[str, int] = {}
        targets: dict[str, int] = {}
        current: dict[str, int] = {}
        moving: list[Room] = []
        for room in self.rooms:
            noon = now.replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
            end = noon if now.timestamp() < noon else now.timestamp() + 3600
            room.woken_until = wake_until(
                self._alarm(room), now.timestamp(), room.woken_until, room.wake_lead, end
            )
            room.state = RoomState(
                window=self._window(room),
                asleep=self._asleep(room) and room.woken_until is None,
                warm=self._warm(room),
                manual=room.manual,
                safety=safety,
                frost=self.frost,
                wind=self.wind and any(self._blind(c) for c in room.covers),
            )
            facing_rain = wet_now and rain_in(room.facing, wind_from, wind_speed)
            if self._door(room):
                # Türen nie unter die Durchgangshöhe, stattdessen eine Meldung
                if facing_rain and room.state.window is not Window.CLOSED and not room.rain_warned:
                    if self.mode != MODE_OFF:
                        room.rain_warned = True
                        self._task(self.messages.async_rain_door(room))
                elif not wet_now:
                    room.rain_warned = False
            else:
                room.state = replace(room.state, rain=facing_rain)
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
            delta = 0
            if self.vacation:
                # bewohnt wirken: jeder Raum folgt der Tagesphase mit eigenem Versatz
                offset, delta = vacation_offset(f"{room.subentry_id}{now.date()}")
                room.vacation_phase = lagged_phase(room.vacation_phase, phase, self._phase_changed, stamp, offset)
                room_house = replace(house, phase=room.vacation_phase)
            else:
                room.vacation_phase = None
            if room.woken_until is not None:
                room_house = replace(room_house, phase=wake_phase(room_house.phase, dark, room.wake_wait))
            room.decision = decide(room.cfg, room.state, room_house, here)
            if self.vacation and room.decision.reason is Reason.SCHEDULE and room_house.phase is not Phase.NIGHT:
                room.decision = Decision(vacation_position(room.decision.position, delta), Reason.VACATION)
            current.update(positions)
            situation_moves = any(s["entity"] == room.situation and s.get("position") is not None for s in room.situations)
            if stand_still(room.decision.reason, room.manual_hold, situation_moves):
                continue  # jeder Behang bleibt, wo er ist, statt auf das Mittel des Raums zu fahren
            if self.mode == MODE_AUTO and may_move(room.decision, room.last_auto_move, stamp, self._rest()):
                for c in positions:
                    targets[c], tilt = self._target(room, c, room_house, here)
                    if tilt is not None:
                        tilts[c] = tilt
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
            await self._send_tilts(tilts)
            for room in moving:
                if sent.intersection(room.covers):
                    room.last_auto_move = stamp

        if self.mode != MODE_OFF:
            self._task(self.messages.async_check(self.rooms, stamp))
        # Entitäten nur neu schreiben, wenn sich etwas geändert hat
        snapshot = (
            self.mode,
            self.phase,
            self.frost,
            self.wind,
            self.vacation,
            tuple(sorted(current.items())),
            tuple((r.decision, r.state, r.manual, r.situation) for r in self.rooms),
        )
        if snapshot == self._snapshot:
            return
        self._snapshot = snapshot
        for update in list(self._listeners):
            update()

    def _target(self, room: Room, cover: str, house: House, here: int) -> tuple[int, int | None]:
        """Position und Lamellenwinkel eines Behangs; der Winkel nur bei Jalousien."""
        if self._curtain(cover):
            return curtain_position(room.decision, house.phase), None
        blind = self._blind(cover)
        decision, state, cfg = room.decision, room.state, room.cfg
        if state.wind and not blind:
            # Sturm hebt nur Jalousien, Rollläden im selben Raum bleiben
            state = replace(state, wind=False)
        if cover in room.cover_azimuth:
            # Eckzimmer: dieser Rollladen sieht die Sonne zu anderen Zeiten als der Raum
            cfg = replace(cfg, sun_azimuth=room.cover_azimuth[cover])
        if state is not room.state or cfg is not room.cfg:
            decision = decide(cfg, state, house, here)
            if decision.reason is Reason.SCHEDULE and room.decision.reason is Reason.VACATION:
                decision = room.decision
        if not blind:
            return decision.position, None
        tilt = blind_tilt(decision.reason, house.phase, int(self.house[CONF_SLAT_TILT]))
        # bei Hitze ganz runter, die schrägen Lamellen lassen Licht herein, aber keine direkte Sonne
        return (0 if decision.reason is Reason.HEAT else decision.position), tilt

    async def _send_tilts(self, tilts: dict[str, int]) -> None:
        for cover, tilt in tilts.items():
            if not tilt_due(tilt, self._tilt_sent.get(cover)):
                continue
            self._tilt_sent[cover] = tilt
            await self.hass.services.async_call(
                "cover", "set_cover_tilt_position", {"tilt_position": tilt}, target={"entity_id": cover}, blocking=False
            )

    def _rest(self) -> float:
        return float(self.house[CONF_REST_MINUTES]) * 60


def _position(state: Any) -> int | None:
    if state is None:
        return None
    value = state.attributes.get("current_position")
    if value is None:
        return {"open": 100, "closed": 0}.get(state.state)
    return int(value)
