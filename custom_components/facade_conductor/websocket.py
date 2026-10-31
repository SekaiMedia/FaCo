"""Schnittstelle der Einstellungsseite: Stand lesen, Räume anlegen, ändern und entfernen.

Gespeichert wird in denselben Einträgen wie über die Dialoge. Jede Änderung lädt die
Integration neu, wie nach „Konfigurieren“.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr

from .config_flow import _area_entities
from .const import (
    CONF_ADVANCED,
    CONF_ANNOUNCE_MANUAL,
    CONF_ANNOUNCE_SAFETY,
    CONF_ANNOUNCE_UNREACHABLE,
    CONF_AREA,
    CONF_COOLING_ABOVE,
    CONF_COOLING_OUTSIDE,
    CONF_COOLING_SENSOR,
    CONF_COVER_DIRECTIONS,
    CONF_COVERS,
    CONF_DIRECTION,
    CONF_DIRECTION_DEG,
    CONF_GROUPS,
    CONF_HOT_TEMPERATURE,
    CONF_LEAVE_CONTACTS,
    CONF_LEAVE_ENABLED,
    CONF_LEAVE_EXCLUDE_PERSONS,
    CONF_LUX_BRIGHT,
    CONF_LUX_DARK,
    CONF_LUX_SENSOR,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_OUTDOOR_TEMP,
    CONF_NOTIFY_MANUAL,
    CONF_NOTIFY_SAFETY,
    CONF_NOTIFY_UNREACHABLE,
    CONF_POSITIONS,
    CONF_RAIN_SENSOR,
    CONF_REST_MINUTES,
    CONF_SAFETY,
    CONF_SITUATIONS,
    CONF_SLEEP_PAUSE_END,
    CONF_SLEEP_PAUSE_START,
    CONF_SLEEP_SENSOR,
    CONF_SLEEP_WAKE_MINUTES,
    CONF_SLEEP_WATTS,
    CONF_SPEAKER,
    CONF_WAKE_LEAD,
    CONF_WAKE_SENSOR,
    CONF_WAKE_WAIT,
    CONF_WEATHER,
    CONF_WINDOW_MEANS,
    CONF_WINDOW_SENSOR,
    DEFAULT_POSITIONS,
    DIRECTION_OPTIONS,
    DOMAIN,
    GROUP_OPTIONS,
    POSITION_KEYS,
    SUBENTRY_ROOM,
    WINDOW_MEANS_OPTIONS,
)
from .leave import phones

TIME_TEXT = vol.Match(r"^\d{2}:\d{2}(:\d{2})?$")
PERCENT = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))

ROOM_CHANGES = vol.Schema(
    {
        vol.Optional(CONF_COVERS): vol.All(cv.ensure_list, [cv.entity_domain("cover")]),
        vol.Optional(CONF_WINDOW_SENSOR): vol.Any(None, cv.entity_domain("binary_sensor")),
        vol.Optional(CONF_WINDOW_MEANS): vol.In(WINDOW_MEANS_OPTIONS),
        vol.Optional(CONF_SLEEP_SENSOR): vol.Any(None, cv.entity_domain(["binary_sensor", "input_boolean", "sensor", "switch"])),
        vol.Optional(CONF_SLEEP_WATTS): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=3000))),
        vol.Optional(CONF_SLEEP_WAKE_MINUTES): vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=0, max=120))),
        vol.Optional(CONF_DIRECTION): vol.In(DIRECTION_OPTIONS),
        vol.Optional(CONF_DIRECTION_DEG): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=360))),
        vol.Optional(CONF_WAKE_SENSOR): vol.Any(None, cv.entity_domain(["sensor", "input_datetime"])),
        vol.Optional(CONF_WAKE_LEAD): vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=0, max=120))),
        vol.Optional(CONF_WAKE_WAIT): bool,
        vol.Optional(CONF_SPEAKER): vol.Any(None, cv.entity_domain("notify")),
        vol.Optional(CONF_COOLING_SENSOR): vol.Any(None, cv.entity_domain("sensor")),
        vol.Optional(CONF_COOLING_ABOVE): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=10, max=40))),
        vol.Optional(CONF_COOLING_OUTSIDE): bool,
        vol.Optional(CONF_COVER_DIRECTIONS): {cv.entity_id: vol.All(vol.Coerce(float), vol.Range(min=0, max=360))},
        vol.Optional(CONF_SITUATIONS): [
            {
                vol.Required("entity"): cv.entity_id,
                vol.Required("states"): vol.All(cv.ensure_list, [cv.string], vol.Length(min=1)),
                vol.Optional("position"): vol.Any(None, PERCENT),
            }
        ],
        vol.Optional(CONF_POSITIONS): {vol.In(POSITION_KEYS): vol.Any(None, PERCENT)},
        vol.Optional(CONF_ADVANCED): {
            vol.In([CONF_SLEEP_PAUSE_START, CONF_SLEEP_PAUSE_END]): vol.Any(None, TIME_TEXT)
        },
    }
)

LUX = vol.All(vol.Coerce(int), vol.Range(min=0, max=100000))
HOUSE_CHANGES = vol.Schema(
    {
        vol.Optional(CONF_WEATHER): vol.Any(None, cv.entity_domain("weather")),
        vol.Optional(CONF_HOT_TEMPERATURE): vol.All(vol.Coerce(float), vol.Range(min=10, max=40)),
        vol.Optional(CONF_LUX_SENSOR): vol.Any(None, cv.entity_domain("sensor")),
        vol.Optional(CONF_LUX_DARK): LUX,
        vol.Optional(CONF_LUX_BRIGHT): LUX,
        vol.Optional(CONF_NIGHT_START): TIME_TEXT,
        vol.Optional(CONF_NIGHT_END): TIME_TEXT,
        vol.Optional(CONF_REST_MINUTES): vol.All(vol.Coerce(int), vol.Range(min=0, max=240)),
        vol.Optional(CONF_POSITIONS): {vol.In(POSITION_KEYS): PERCENT},
        vol.Optional(CONF_LEAVE_ENABLED): bool,
        vol.Optional(CONF_NOTIFY_UNREACHABLE): bool,
        vol.Optional(CONF_NOTIFY_MANUAL): bool,
        vol.Optional(CONF_ANNOUNCE_UNREACHABLE): bool,
        vol.Optional(CONF_ANNOUNCE_MANUAL): bool,
        vol.Optional(CONF_NOTIFY_SAFETY): bool,
        vol.Optional(CONF_ANNOUNCE_SAFETY): bool,
        vol.Optional(CONF_OUTDOOR_TEMP): vol.Any(None, cv.entity_domain("sensor")),
        vol.Optional(CONF_RAIN_SENSOR): vol.Any(None, cv.entity_domain(["sensor", "binary_sensor"])),
        vol.Optional(CONF_SPEAKER): vol.Any(None, cv.entity_domain("notify")),
        vol.Optional(CONF_GROUPS): vol.All(cv.ensure_list, [vol.In(GROUP_OPTIONS)]),
        vol.Optional(CONF_SAFETY): [
            {
                vol.Required("entity"): cv.entity_id,
                vol.Required("states"): vol.All(cv.ensure_list, [cv.string], vol.Length(min=1)),
                vol.Optional("home"): vol.Any(None, PERCENT),
                vol.Optional("away"): vol.Any(None, PERCENT),
            }
        ],
        vol.Optional(CONF_LEAVE_CONTACTS): vol.All(cv.ensure_list, [cv.entity_domain("binary_sensor")]),
        vol.Optional(CONF_LEAVE_EXCLUDE_PERSONS): vol.All(cv.ensure_list, [cv.entity_domain("person")]),
    }
)
HOUSE_KEYS = [k.schema for k in HOUSE_CHANGES.schema if k.schema != CONF_POSITIONS]


@callback
def async_register(hass: HomeAssistant) -> None:
    for command in (
        ws_info,
        ws_house_update,
        ws_leave_test,
        ws_room_add,
        ws_room_update,
        ws_room_remove,
        ws_aliases,
    ):
        websocket_api.async_register_command(hass, command)


def _entry(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> ConfigEntry | None:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_loaded", "Facade Conductor ist nicht geladen")
        return None
    return entries[0]


def _room(entry: ConfigEntry, connection: websocket_api.ActiveConnection, msg: dict) -> ConfigSubentry | None:
    sub = entry.subentries.get(msg["room_id"])
    if sub is None or sub.subentry_type != SUBENTRY_ROOM:
        connection.send_error(msg["id"], "not_found", "Raum nicht gefunden")
        return None
    return sub


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/info"})
@websocket_api.require_admin
@callback
def ws_info(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if (entry := _entry(hass, connection, msg)) is None:
        return
    conductor = entry.runtime_data
    ent_reg = er.async_get(hass)
    live = {room.subentry_id: room for room in conductor.rooms}
    rooms = []
    for sub in entry.subentries.values():
        if sub.subentry_type != SUBENTRY_ROOM:
            continue
        room = live.get(sub.subentry_id)
        decision = room.decision if room else None
        current = conductor._current(room) if room else {}
        rooms.append(
            {
                "id": sub.subentry_id,
                "name": sub.title,
                "data": dict(sub.data),
                "position": round(sum(current.values()) / len(current)) if current else None,
                "target": decision.position if decision else None,
                "reason": decision.reason.value if decision else None,
                "situation": room.situation if room else None,
                "reason_entity": ent_reg.async_get_entity_id("sensor", DOMAIN, f"{sub.subentry_id}_reason"),
                "manual_entity": ent_reg.async_get_entity_id("switch", DOMAIN, f"{sub.subentry_id}_manual"),
            }
        )
    connection.send_result(
        msg["id"],
        {
            "mode": conductor.mode,
            "mode_entity": ent_reg.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_mode"),
            "phase": conductor.phase.value if conductor.phase else None,
            "frost": conductor.frost,
            "house": {k: conductor.house.get(k) for k in HOUSE_KEYS},
            "positions": {k: int(v) for k, v in {**DEFAULT_POSITIONS, **conductor.house.get(CONF_POSITIONS, {})}.items()},
            "rooms": sorted(rooms, key=lambda r: r["name"].casefold()),
            # alle Personen, auch ausgeschlossene, damit man sie wieder einschalten kann
            "voice": _voice(hass, entry),
            "persons": [
                {"id": p, "phones": phones(hass, p)} for p in sorted(hass.states.async_entity_ids("person"))
            ],
        },
    )


def _voice(hass: HomeAssistant, entry: ConfigEntry) -> list[dict[str, Any]]:
    """Die Gruppen mit ihren Sprachnamen, dazu Art und Name für die Vorschläge."""
    rooms = {s.subentry_id: s.title for s in entry.subentries.values()}
    floors = fr.async_get(hass)
    floor_prefix = f"{entry.entry_id}_floor_"
    groups = []
    for reg in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if reg.domain != "cover":
            continue
        if reg.unique_id.endswith("_room_covers"):
            kind, name = "room", rooms.get(reg.unique_id.removesuffix("_room_covers"))
        elif reg.unique_id.startswith(floor_prefix):
            floor = floors.async_get_floor(reg.unique_id.removeprefix(floor_prefix))
            kind, name = "floor", floor.name if floor else None
        else:
            kind, name = "house", None
        # ein Eintrag ohne Text steht in neueren Versionen für den Namen der Entität selbst
        aliases = sorted(a for a in reg.aliases if isinstance(a, str))
        groups.append({"entity_id": reg.entity_id, "kind": kind, "name": name, "aliases": aliases})
    order = {"house": 0, "floor": 1, "room": 2}
    return sorted(groups, key=lambda g: (order[g["kind"]], (g["name"] or "").casefold()))


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/house/update", vol.Required("changes"): HOUSE_CHANGES}
)
@websocket_api.require_admin
@callback
def ws_house_update(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Wie „Konfigurieren“ beim Haus: Änderungen landen in den Optionen."""
    if (entry := _entry(hass, connection, msg)) is None:
        return
    changes = dict(msg["changes"])
    current = entry.runtime_data.house
    if CONF_POSITIONS in changes:
        changes[CONF_POSITIONS] = {**current.get(CONF_POSITIONS, {}), **changes[CONF_POSITIONS]}
    merged = {**current, **changes}
    if merged[CONF_LUX_DARK] >= merged[CONF_LUX_BRIGHT]:
        connection.send_error(msg["id"], "invalid_format", "Dunkel muss unter hell liegen")
        return
    hass.config_entries.async_update_entry(entry, options={**entry.options, **changes})
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/leave/test", vol.Required("person"): cv.entity_domain("person")}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_leave_test(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Testmeldung, damit man sieht, auf welchem Handy die Warnung ankommt."""
    if (entry := _entry(hass, connection, msg)) is None:
        return
    connection.send_result(msg["id"], {"sent": await entry.runtime_data.leave.async_test(msg["person"])})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/aliases",
        vol.Required("entity_id"): cv.entity_domain("cover"),
        vol.Required("aliases"): [cv.string],
    }
)
@websocket_api.require_admin
@callback
def ws_aliases(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Sprachnamen einer eigenen Gruppe setzen. Lädt die Integration nicht neu."""
    if (entry := _entry(hass, connection, msg)) is None:
        return
    ent_reg = er.async_get(hass)
    reg = ent_reg.async_get(msg["entity_id"])
    if reg is None or reg.config_entry_id != entry.entry_id:
        connection.send_error(msg["id"], "not_found", "Keine Gruppe von Facade Conductor")
        return
    names = list(dict.fromkeys(a.strip() for a in msg["aliases"] if a.strip()))
    # Einträge ohne Text (der Name selbst) bleiben stehen
    aliases = [a for a in reg.aliases if not isinstance(a, str)] + names
    ent_reg.async_update_entity(reg.entity_id, aliases=set(aliases) if isinstance(reg.aliases, set) else aliases)
    connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/room/add", vol.Required("area"): str})
@websocket_api.require_admin
@callback
def ws_room_add(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Raum aus einem Bereich anlegen, Rollläden und Fensterkontakt darin vorschlagen."""
    if (entry := _entry(hass, connection, msg)) is None:
        return
    area = ar.async_get(hass).async_get_area(msg["area"])
    if area is None:
        connection.send_error(msg["id"], "not_found", "Bereich nicht gefunden")
        return
    if any(s.data.get(CONF_AREA) == area.id for s in entry.subentries.values()):
        connection.send_error(msg["id"], "already_configured", "Für diesen Bereich gibt es schon einen Raum")
        return
    windows = _area_entities(hass, area.id, "binary_sensor", {"window", "door", "opening"})
    data = {
        CONF_AREA: area.id,
        CONF_COVERS: _area_entities(hass, area.id, "cover"),
        CONF_WINDOW_SENSOR: windows[0] if windows else None,
        CONF_DIRECTION: "none",
    }
    sub = ConfigSubentry(data=MappingProxyType(data), subentry_type=SUBENTRY_ROOM, title=area.name, unique_id=None)
    hass.config_entries.async_add_subentry(entry, sub)
    connection.send_result(msg["id"], {"id": sub.subentry_id})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/room/update",
        vol.Required("room_id"): str,
        vol.Required("changes"): ROOM_CHANGES,
    }
)
@websocket_api.require_admin
@callback
def ws_room_update(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if (entry := _entry(hass, connection, msg)) is None or (sub := _room(entry, connection, msg)) is None:
        return
    data: dict[str, Any] = {**sub.data, **msg["changes"]}
    hass.config_entries.async_update_subentry(entry, sub, data=data)
    connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/room/remove", vol.Required("room_id"): str})
@websocket_api.require_admin
@callback
def ws_room_remove(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if (entry := _entry(hass, connection, msg)) is None or _room(entry, connection, msg) is None:
        return
    hass.config_entries.async_remove_subentry(entry, msg["room_id"])
    connection.send_result(msg["id"])
