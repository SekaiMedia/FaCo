"""Meldungen: Rollladen nicht erreichbar, Handbetrieb mit Knopf „Automatik fortsetzen“, Sicherheit.

Push geht an die Handys des Haushalts, wie bei der Warnung beim Verlassen. Durchsagen gehen an den
Lautsprecher des Raums, sonst an den des Hauses, und schweigen nachts und solange jemand schläft,
außer bei Sicherheit. Ein nicht erreichbarer Rollladen steht zusätzlich bei den Reparaturen.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import (
    CONF_ANNOUNCE_MANUAL,
    CONF_ANNOUNCE_SAFETY,
    CONF_ANNOUNCE_UNREACHABLE,
    CONF_NOTIFY_MANUAL,
    CONF_NOTIFY_SAFETY,
    CONF_NOTIFY_UNREACHABLE,
    CONF_SPEAKER,
    DOMAIN,
)
from .engine import due_unreachable, may_announce
from .leave import async_notify, phones

if TYPE_CHECKING:
    from .conductor import Room

_LOGGER = logging.getLogger(__name__)

ACTION_RESUME = "FACO_RESUME_"

TEXTS = {
    "de": {
        "unreachable": "{room}: {cover} ist seit 15 Minuten nicht erreichbar.",
        "manual": "{room}: Handbetrieb bis zur nächsten Tagesphase.",
        "resume": "Automatik fortsetzen",
        "safety": "Sicherheit: {trigger}. Die Rollläden fahren auf {position} Prozent.",
    },
    "en": {
        "unreachable": "{room}: {cover} has been unreachable for 15 minutes.",
        "manual": "{room}: manual mode until the next phase of the day.",
        "resume": "Resume automatic",
        "safety": "Safety: {trigger}. The shutters move to {position} percent.",
    },
}


class Messages:
    def __init__(
        self,
        hass: HomeAssistant,
        house: dict[str, Any],
        persons: Callable[[], list[str]],
        resume: Callable[[str], None],
        quiet: Callable[[], bool],
    ) -> None:
        self.hass = hass
        self.unreachable = bool(house[CONF_NOTIFY_UNREACHABLE])
        self.manual = bool(house[CONF_NOTIFY_MANUAL])
        self.say_unreachable = bool(house[CONF_ANNOUNCE_UNREACHABLE])
        self.say_manual = bool(house[CONF_ANNOUNCE_MANUAL])
        self.safety = bool(house[CONF_NOTIFY_SAFETY])
        self.say_safety = bool(house[CONF_ANNOUNCE_SAFETY])
        self.speaker = house.get(CONF_SPEAKER)
        self._quiet = quiet
        self._said: dict[str, float] = {}
        self._persons = persons
        self._resume = resume
        self._down: dict[str, float] = {}
        self._sent: set[str] = set()
        self._unsub: CALLBACK_TYPE | None = None

    def _text(self, key: str, **values: str) -> str:
        lang = "de" if (self.hass.config.language or "").startswith("de") else "en"
        return TEXTS[lang][key].format(**values)

    @callback
    def async_start(self) -> None:
        # Einträge von vor dem Neustart: ob der Rollladen noch fehlt, zeigt sich nach 15 Minuten neu
        for domain, issue_id in list(ir.async_get(self.hass).issues):
            if domain == DOMAIN and issue_id.startswith("unreachable_"):
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        if self.manual:
            self._unsub = self.hass.bus.async_listen("mobile_app_notification_action", self._on_action)

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
            text = self._text("unreachable", room=owner[cover].name, cover=name)
            if self.unreachable:
                await self._send(text, {"tag": f"faco_{cover}"})
            if self.say_unreachable:
                await self._say(owner[cover].speaker or self.speaker, text, f"unreachable_{cover}")

    async def async_manual(self, room: Room) -> None:
        if self.say_manual:
            await self._say(room.speaker or self.speaker, self._text("manual", room=room.name), f"manual_{room.subentry_id}")
        if not self.manual:
            return
        await self._send(
            self._text("manual", room=room.name),
            {
                "tag": f"faco_manual_{room.subentry_id}",
                "actions": [{"action": f"{ACTION_RESUME}{room.subentry_id}", "title": self._text("resume")}],
            },
        )

    async def async_safety(self, trigger: str, position: int) -> None:
        """Ein Sicherheits-Auslöser fährt die Rollläden; die Durchsage kommt auch nachts."""
        state = self.hass.states.get(trigger)
        text = self._text("safety", trigger=state.name if state else trigger, position=str(position))
        if self.safety:
            await self._send(text, {"tag": "faco_safety", "priority": "high", "ttl": 0})
        if self.say_safety:
            await self._say(self.speaker, text, f"safety_{trigger}", urgent=True)
