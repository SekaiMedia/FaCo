"""Gemeinsame Grundlage der Entitäten eines Raums: Gerät, Aktualisierung, Verfügbarkeit."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .conductor import Conductor, Room
from .const import DOMAIN, MODE_OFF


def remove_stale(hass: HomeAssistant, entry_id: str, domain: str, entities: list[Entity]) -> None:
    """Entitäten, die es nicht mehr gibt (Ebene abgewählt, Sensor entfernt), nicht verwaist liegen lassen."""
    wanted = {e.unique_id for e in entities}
    ent_reg = er.async_get(hass)
    for old in er.async_entries_for_config_entry(ent_reg, entry_id):
        if old.domain == domain and old.unique_id not in wanted:
            ent_reg.async_remove(old.entity_id)


def hub_device(entry_id: str) -> DeviceInfo:
    """Das Hausgerät „Facade Conductor“, an dem Betriebsart, Urlaub und die Hausgruppen hängen."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="Facade Conductor",
        manufacturer="SekaiMedia",
        entry_type=DeviceEntryType.SERVICE,
    )


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
