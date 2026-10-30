"""Gemeinsame Grundlage der Entitäten eines Raums: Gerät, Aktualisierung, Verfügbarkeit."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .conductor import Conductor, Room
from .const import DOMAIN, MODE_OFF


class RoomEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, conductor: Conductor, room: Room, key: str) -> None:
        self._conductor = conductor
        self._room = room
        self._attr_translation_key = key
        self._attr_unique_id = f"{room.subentry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, room.subentry_id)},
            name=room.name,
            manufacturer="SekaiMedia",
            model="Facade Conductor",
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, conductor.entry.entry_id),
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._conductor.add_listener(self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._conductor.mode != MODE_OFF and self._room.decision is not None
