"""Meldungen per Push und Durchsage, je Ereignis wählbar.

Push geht an die Handys des Haushalts, wie bei der Warnung beim Verlassen. Durchsagen gehen an den
Lautsprecher des Raums, sonst an den des Hauses, und schweigen nachts und solange jemand schläft,
außer bei Sicherheit. Jede Push-Meldung hat „Heute nicht mehr melden“, ein nicht erreichbarer
Rollladen zusätzlich „Erneut versuchen“ und einen Eintrag bei den Reparaturen.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from .const import CONF_SPEAKER, DOMAIN, EVENTS
from .engine import due_unreachable, may_announce
from .leave import async_notify, phones

if TYPE_CHECKING:
    from .conductor import Room

_LOGGER = logging.getLogger(__name__)

ACTION_RESUME = "FACO_RESUME_"
ACTION_RETRY = "FACO_RETRY_"
ACTION_MUTE = "FACO_MUTE_"

TEXTS = {
    "de": {
        "unreachable": "{room}: {cover} ist seit 15 Minuten nicht erreichbar.",
        "manual": "{room}: Handbetrieb bis zur nächsten Tagesphase.",
        "resume": "Automatik fortsetzen",
        "retry": "Erneut versuchen",
        "mute": "Heute nicht mehr melden",
        "safety": "Sicherheit: {trigger}. Die Rollläden fahren auf {position} Prozent.",
        "rain_door": "{room}: Regen auf die offene Tür.",
        "rain_window": "{room}: Regen auf das offene Fenster.",
        "tilted_cold": "{room}: Das Fenster ist seit 15 Minuten gekippt. Dauerkippen kostet Heizung, lieber kurz ganz öffnen.",
        "open_cold": "{room}: Das Fenster ist seit 10 Minuten offen, draußen {outside} Grad. Stoßlüften reicht.",
        "heat": "{room}: Draußen {outside} Grad, drinnen {inside} Grad. Fenster besser schließen.",
        "alarm": "Alarm scharf, noch offen: {names}.",
        "humid": "{room}: Seit 2 Stunden über 65 Prozent Feuchte. Jetzt lüften, draußen ist es trockener.",
        "humid_open": "{room}: Fenster offen, aber draußen ist es schwül. Fenster zu.",
        "mold": "{room}: Schimmelgefahr an der kältesten Stelle. Jetzt lüften.",
    },
    "en": {
        "unreachable": "{room}: {cover} has been unreachable for 15 minutes.",
        "manual": "{room}: manual mode until the next phase of the day.",
        "resume": "Resume automatic",
        "retry": "Try again",
        "mute": "Not again today",
        "safety": "Safety: {trigger}. The shutters move to {position} percent.",
        "rain_door": "{room}: rain on the open door.",
        "rain_window": "{room}: rain on the open window.",
        "tilted_cold": "{room}: the window has been tilted for 15 minutes. Constant tilting costs heating, better open it fully for a short time.",
        "open_cold": "{room}: the window has been open for 10 minutes, {outside} degrees outside. A short airing is enough.",
        "heat": "{room}: {outside} degrees outside, {inside} degrees inside. Better close the window.",
        "alarm": "Alarm armed, still open: {names}.",
        "humid": "{room}: above 65 percent humidity for 2 hours. Air now, it is drier outside.",
        "humid_open": "{room}: window open, but it is humid outside. Close the window.",
        "mold": "{room}: risk of mould at the coldest spot. Air now.",
    },
}

# welcher Text zu welchem Ereignis gehört, für die Wahl Push oder Durchsage
HINT_EVENT = {"tilted_cold": "window", "open_cold": "window", "heat": "window", "humid": "climate",
              "humid_open": "climate", "mold": "climate"}


class Messages:
    def __init__(
        self,
        hass: HomeAssistant,
        house: dict[str, Any],
        persons: Callable[[], list[str]],
        resume: Callable[[str], None],
        quiet: Callable[[], bool],
        retry: Callable[[str], None],
    ) -> None:
        self.hass = hass
        self.push = {e: bool(house.get(f"notify_{e}")) for e in EVENTS}
        self.say = {e: bool(house.get(f"announce_{e}")) for e in EVENTS}
        self.speaker = house.get(CONF_SPEAKER)
        self._quiet = quiet
        self._said: dict[str, float] = {}
        self._persons = persons
        self._resume = resume
        self._retry = retry
        self._down: dict[str, float] = {}
        self._sent: set[str] = set()
        self._muted: dict[str, date] = {}
        self._unsub: CALLBACK_TYPE | None = None

    def _text(self, key: str, **values: Any) -> str:
        lang = "de" if (self.hass.config.language or "").startswith("de") else "en"
        return TEXTS[lang][key].format(**values)

    @callback
    def async_start(self) -> None:
        # Einträge von vor dem Neustart: ob der Rollladen noch fehlt, zeigt sich nach 15 Minuten neu.
        # Nach dem Neuladen beim Speichern bleiben die gemerkten Ausfälle und ihre Einträge stehen.
        for domain, issue_id in list(ir.async_get(self.hass).issues):
            if domain == DOMAIN and issue_id.startswith("unreachable_") and issue_id[12:] not in self._sent:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self._unsub = self.hass.bus.async_listen("mobile_app_notification_action", self._on_action)

    def kept(self) -> tuple[dict[str, float], set[str], dict[str, date]]:
        return self._down, self._sent, self._muted

    def restore(self, kept: tuple[dict[str, float], set[str], dict[str, date]]) -> None:
        self._down, self._sent, self._muted = kept

    @callback
    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _on_action(self, event: Event) -> None:
        action = event.data.get("action") or ""
        if action.startswith(ACTION_RESUME):
            self._resume(action.removeprefix(ACTION_RESUME))
        elif action.startswith(ACTION_RETRY):
            self._retry(action.removeprefix(ACTION_RETRY))
        elif action.startswith(ACTION_MUTE):
            self._muted[action.removeprefix(ACTION_MUTE)] = dt_util.now().date()

    async def _send(self, message: str, data: dict[str, Any]) -> None:
        for service in (s for p in self._persons() for s in phones(self.hass, p)):
            await async_notify(self.hass, service, message, data)

    async def _say(self, target: str | None, message: str, key: str, urgent: bool = False) -> None:
        if not target or not may_announce(key, time.monotonic(), self._said, self._quiet() and not urgent):
            return
        try:
            await self.hass.services.async_call(
                "notify", "send_message", {"message": message}, target={"entity_id": target}, blocking=True
            )
        except Exception:  # noqa: BLE001 - ein stummer Lautsprecher darf den Takt nicht aufhalten
            _LOGGER.warning("Durchsage an %s fehlgeschlagen", target)

    async def async_event(
        self,
        event: str,
        text: str,
        tag: str,
        speaker: str | None = None,
        actions: list[dict[str, str]] | None = None,
        urgent: bool = False,
    ) -> None:
        """Eine Meldung als Push und/oder Durchsage, je nachdem, was für dieses Ereignis gewählt ist."""
        if self._muted.get(tag) == dt_util.now().date():
            return
        if self.push[event]:
            buttons = list(actions or [])
            data: dict[str, Any] = {"tag": tag}
            if urgent:
                data |= {"priority": "high", "ttl": 0}
            else:
                buttons.append({"action": f"{ACTION_MUTE}{tag}", "title": self._text("mute")})
            await self._send(text, data | {"actions": buttons})
        if self.say[event]:
            await self._say(speaker or self.speaker, text, tag, urgent)

    async def async_check(self, rooms: list[Room], now: float) -> None:
        owner = {c: room for room in rooms for c in room.covers}
        down = {c for c in owner if (s := self.hass.states.get(c)) is None or s.state == STATE_UNAVAILABLE}
        reported = set(self._sent)
        due = due_unreachable(self._down, self._sent, down, now)
        for cover in reported - self._sent:
            ir.async_delete_issue(self.hass, DOMAIN, f"unreachable_{cover}")
        for cover in due:
            state = self.hass.states.get(cover)
            name = state.name if state else cover
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"unreachable_{cover}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="unreachable",
                translation_placeholders={"cover": name, "room": owner[cover].name},
            )
            await self.async_event(
                "unreachable",
                self._text("unreachable", room=owner[cover].name, cover=name),
                f"faco_{cover}",
                owner[cover].speaker,
                [{"action": f"{ACTION_RETRY}{cover}", "title": self._text("retry")}],
            )

    async def async_manual(self, room: Room) -> None:
        await self.async_event(
            "manual",
            self._text("manual", room=room.name),
            f"faco_manual_{room.subentry_id}",
            room.speaker,
            [{"action": f"{ACTION_RESUME}{room.subentry_id}", "title": self._text("resume")}],
        )

    async def async_safety(self, trigger: str, position: int) -> None:
        """Ein Sicherheits-Auslöser fährt die Rollläden; die Durchsage kommt auch nachts."""
        state = self.hass.states.get(trigger)
        text = self._text("safety", trigger=state.name if state else trigger, position=position)
        await self.async_event("safety", text, f"faco_safety_{trigger}", urgent=True)

    async def async_rain(self, room: Room, door: bool) -> None:
        """Türen fahren bei Regen nicht unter die Durchgangshöhe; ganz offene Fenster melden zusätzlich."""
        text = self._text("rain_door" if door else "rain_window", room=room.name)
        await self.async_event("rain", text, f"faco_rain_{room.subentry_id}", room.speaker)

    async def async_hint(self, room: Room, hint: str, **values: Any) -> None:
        text = self._text(hint, room=room.name, **values)
        await self.async_event(HINT_EVENT[hint], text, f"faco_{hint}_{room.subentry_id}", room.speaker)

    async def async_alarm(self, names: list[str]) -> None:
        await self.async_event("alarm", self._text("alarm", names=", ".join(names)), "faco_alarm")
