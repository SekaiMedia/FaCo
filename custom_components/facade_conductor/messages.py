"""Meldungen aufs Handy: Rollladen nicht erreichbar, Handbetrieb mit Knopf „Automatik fortsetzen“.

Empfänger sind die Handys des Haushalts, wie bei der Warnung beim Verlassen.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback

from .const import CONF_NOTIFY_MANUAL, CONF_NOTIFY_UNREACHABLE
from .engine import due_unreachable
from .leave import async_notify, phones

if TYPE_CHECKING:
    from .conductor import Room

ACTION_RESUME = "FACO_RESUME_"

TEXTS = {
    "de": {
        "unreachable": "{room}: {cover} ist seit 15 Minuten nicht erreichbar.",
        "manual": "{room}: Handbetrieb bis zur nächsten Tagesphase.",
        "resume": "Automatik fortsetzen",
    },
    "en": {
        "unreachable": "{room}: {cover} has been unreachable for 15 minutes.",
        "manual": "{room}: manual mode until the next phase of the day.",
        "resume": "Resume automatic",
    },
}


class Messages:
    def __init__(
        self, hass: HomeAssistant, house: dict[str, Any], persons: Callable[[], list[str]], resume: Callable[[str], None]
    ) -> None:
        self.hass = hass
        self.unreachable = bool(house[CONF_NOTIFY_UNREACHABLE])
        self.manual = bool(house[CONF_NOTIFY_MANUAL])
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

    async def async_check(self, rooms: list[Room], now: float) -> None:
        if not self.unreachable:
            return
        owner = {c: room for room in rooms for c in room.covers}
        down = {c for c in owner if (s := self.hass.states.get(c)) is None or s.state == STATE_UNAVAILABLE}
        for cover in due_unreachable(self._down, self._sent, down, now):
            state = self.hass.states.get(cover)
            name = state.name if state else cover
            await self._send(self._text("unreachable", room=owner[cover].name, cover=name), {"tag": f"faco_{cover}"})

    async def async_manual(self, room: Room) -> None:
        if not self.manual:
            return
        await self._send(
            self._text("manual", room=room.name),
            {
                "tag": f"faco_manual_{room.subentry_id}",
                "actions": [{"action": f"{ACTION_RESUME}{room.subentry_id}", "title": self._text("resume")}],
            },
        )
