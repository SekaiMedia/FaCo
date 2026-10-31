"""Je Raum: Handbetrieb sehen und beenden, auch aus Automationen heraus. Fürs Haus: Urlaub."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import FacadeConfigEntry
from .conductor import Conductor, Room
from .const import MODE_AUTO
from .entity import RoomEntity, hub_device


async def async_setup_entry(
    hass: HomeAssistant, entry: FacadeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    conductor = entry.runtime_data
    async_add_entities([VacationSwitch(entry)])
    for room in conductor.rooms:
        async_add_entities([ManualSwitch(conductor, room)], config_subentry_id=room.subentry_id)


class ManualSwitch(RoomEntity, SwitchEntity):
    """An: FaCo lässt den Raum, wie er ist. Aus: die Automatik übernimmt wieder."""

    def __init__(self, conductor: Conductor, room: Room) -> None:
        super().__init__(conductor, room, "manual")

    @property
    def available(self) -> bool:
        # Handbetrieb gibt es nur, wenn FaCo selbst fährt
        return self._conductor.mode == MODE_AUTO and self._room.decision is not None

    @property
    def is_on(self) -> bool:
        return self._room.manual is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._conductor.set_manual(self._room, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._conductor.set_manual(self._room, False)


class VacationSwitch(SwitchEntity, RestoreEntity):
    """Urlaub: normaler Tagesablauf, aber je Raum leicht versetzt, damit das Haus bewohnt wirkt."""

    _attr_has_entity_name = True
    _attr_translation_key = "vacation"

    def __init__(self, entry: FacadeConfigEntry) -> None:
        self._conductor = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_vacation"
        self._attr_is_on = False
        self._attr_device_info = hub_device(entry.entry_id)

    async def async_added_to_hass(self) -> None:
        if (last := await self.async_get_last_state()) and last.state == "on":
            self._attr_is_on = True
        self._conductor.set_vacation(self._attr_is_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self._conductor.set_vacation(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self._conductor.set_vacation(False)
        self.async_write_ha_state()
