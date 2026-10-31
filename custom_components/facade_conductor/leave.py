"""Beim Verlassen: Geht die letzte Person und eine gewählte Tür oder ein Fenster ist offen, kommt eine Push-Meldung.

Erst an die gehende Person mit den Knöpfen „Ich kehre um“ und „Ist gewollt“, bei offenen Türen
ohne Antwort später an alle anderen. Gemeldet wird über die Handy-App von Home Assistant.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.const import STATE_HOME, STATE_ON
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import slugify

from .const import CONF_LEAVE_CONTACTS, CONF_LEAVE_ENABLED, CONF_LEAVE_EXCLUDE_PERSONS
from .engine import LEAVE_DONE, LEAVE_WAITING, leave_step

_LOGGER = logging.getLogger(__name__)

ACTION_RETURN = "FACO_LEAVE_RETURN"
ACTION_OK = "FACO_LEAVE_OK"
TAG = "faco_leave"
DOOR_CLASSES = {"door", "garage_door"}

TEXTS = {
    "de": {
        "one": "{names} ist noch offen.",
        "many": "Noch offen: {names}.",
        "others": "Niemand ist zu Hause und {person} hat nicht reagiert. {open}",
        "return": "Ich kehre um",
        "ok": "Ist gewollt",
        "test": "Testmeldung von Facade Conductor: Beim Verlassen kommt die Warnung auf dieses Handy.",
    },
    "en": {
        "one": "{names} is still open.",
        "many": "Still open: {names}.",
        "others": "Nobody is home and {person} did not respond. {open}",
        "return": "I'm going back",
        "ok": "It's intended",
        "test": "Test message from Facade Conductor: the leaving warning will arrive on this phone.",
    },
}


def phones(hass: HomeAssistant, person_id: str) -> list[str]:
    """Notify-Dienste der Handy-App einer Person, gefunden über ihre Geräte-Tracker."""
    state = hass.states.get(person_id)
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    found = []
    for tracker in state.attributes.get("device_trackers", []) if state else []:
        entry = ent_reg.async_get(tracker)
        if entry is None or entry.platform != "mobile_app" or entry.device_id is None:
            continue
        device = dev_reg.async_get(entry.device_id)
        # die App benennt ihren Dienst nach dem Gerätenamen bei der Anmeldung, nicht nach einer Umbenennung
        service = f"mobile_app_{slugify(device.name)}" if device and device.name else None
        if service and hass.services.has_service("notify", service):
            found.append(service)
    return found


@dataclass
class Alert:
    person: str
    since: float
    stage: int = LEAVE_WAITING
    warned: list[str] = field(default_factory=list)


class LeaveWatcher:
    def __init__(self, hass: HomeAssistant, house: dict[str, Any], active: Callable[[], bool]) -> None:
        self.hass = hass
        self.enabled = bool(house[CONF_LEAVE_ENABLED])
        self.contacts = list(house[CONF_LEAVE_CONTACTS])
        self._exclude = set(house[CONF_LEAVE_EXCLUDE_PERSONS])
        self._active = active
        self.alert: Alert | None = None
        self._unsubs: list[CALLBACK_TYPE] = []

    @property
    def persons(self) -> list[str]:
        return sorted(p for p in self.hass.states.async_entity_ids("person") if p not in self._exclude)

    def _text(self, key: str, **values: str) -> str:
        lang = "de" if (self.hass.config.language or "").startswith("de") else "en"
        return TEXTS[lang][key].format(**values)

    async def async_start(self) -> None:
        if not self.enabled or not self.contacts:
            return
        self._unsubs.append(async_track_state_change_event(self.hass, self.persons, self._on_person))
        self._unsubs.append(async_track_state_change_event(self.hass, self.contacts, self._on_change))
        self._unsubs.append(async_track_time_interval(self.hass, self._tick, timedelta(seconds=30)))
        self._unsubs.append(self.hass.bus.async_listen("mobile_app_notification_action", self._on_action))

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    # Lage

    def _anyone_home(self) -> bool:
        return any((s := self.hass.states.get(p)) and s.state == STATE_HOME for p in self.persons)

    def _open(self) -> tuple[list[str], list[str]]:
        doors, windows = [], []
        for entity_id in self.contacts:
            state = self.hass.states.get(entity_id)
            if state and state.state == STATE_ON:
                (doors if state.attributes.get("device_class") in DOOR_CLASSES else windows).append(entity_id)
        return doors, windows

    def _message(self, entity_ids: list[str]) -> str:
        names = [(s.name if (s := self.hass.states.get(e)) else e) for e in entity_ids]
        return self._text("one" if len(names) == 1 else "many", names=", ".join(names))

    # Ereignisse

    @callback
    def _on_person(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        left = old is not None and old.state == STATE_HOME and new is not None and new.state != STATE_HOME
        if left and self._active() and not self._anyone_home():
            self.alert = Alert(person=event.data["entity_id"], since=time.monotonic())
        self.hass.async_create_task(self._tick())

    @callback
    def _on_change(self, _event: Event[EventStateChangedData]) -> None:
        self.hass.async_create_task(self._tick())

    @callback
    def _on_action(self, event: Event) -> None:
        if self.alert and event.data.get("action") in (ACTION_RETURN, ACTION_OK):
            # beides stoppt die Weiterleitung; wer umkehrt, kümmert sich selbst
            self.alert.stage = LEAVE_DONE
            self.hass.async_create_task(self._tick())

    async def _tick(self, _now: Any = None) -> None:
        alert = self.alert
        if alert is None:
            return
        doors, windows = self._open()
        stage, action = leave_step(
            alert.stage, alert.since, time.monotonic(), self._anyone_home(), bool(doors), bool(windows)
        )
        alert.stage = stage
        if action == "warn_person":
            await self._send(phones(self.hass, alert.person), self._message(doors + windows), actions=True)
        elif action == "warn_others":
            others = [s for p in self.persons if p != alert.person for s in phones(self.hass, p)]
            person = self.hass.states.get(alert.person)
            text = self._text("others", person=person.name if person else alert.person, open=self._message(doors))
            await self._send(others, text, actions=False)
        if stage == LEAVE_DONE:
            self.alert = None
            # erledigte Meldungen von den Handys nehmen
            for service in alert.warned:
                await self._notify(service, "clear_notification", {"tag": TAG})

    async def _send(self, services: list[str], message: str, actions: bool) -> None:
        data: dict[str, Any] = {"tag": TAG}
        if actions:
            data["actions"] = [
                {"action": ACTION_RETURN, "title": self._text("return")},
                {"action": ACTION_OK, "title": self._text("ok")},
            ]
        for service in services:
            await self._notify(service, message, data)
            if self.alert is not None:
                self.alert.warned.append(service)

    async def _notify(self, service: str, message: str, data: dict[str, Any]) -> None:
        try:
            await self.hass.services.async_call(
                "notify", service, {"title": "Facade Conductor", "message": message, "data": data}, blocking=True
            )
        except Exception:  # noqa: BLE001 - ein ausgeschaltetes Handy darf die anderen Meldungen nicht aufhalten
            _LOGGER.warning("Meldung an %s fehlgeschlagen", service)

    async def async_test(self, person_id: str) -> int:
        """Testmeldung an alle Handys einer Person; zählt, wohin sie ging."""
        services = phones(self.hass, person_id)
        for service in services:
            await self._notify(service, self._text("test"), {})
        return len(services)
