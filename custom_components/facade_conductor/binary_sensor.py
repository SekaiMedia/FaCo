"""Je Raum: ob FaCo ihn gerade als schlafend behandelt, Aufstehpause eingerechnet."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FacadeConfigEntry
from .conductor import Conductor, Room
from .const import MODE_OFF
from .entity import RoomEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: FacadeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    conductor = entry.runtime_data
    for room in conductor.rooms:
        if room.sleep_sensor:
            async_add_entities([AsleepSensor(conductor, room)], config_subentry_id=room.subentry_id)


class AsleepSensor(RoomEntity, BinarySensorEntity):
    def __init__(self, conductor: Conductor, room: Room) -> None:
        super().__init__(conductor, room, "asleep")

    @property
    def available(self) -> bool:
        return self._conductor.mode != MODE_OFF and self._room.state is not None

    @property
    def is_on(self) -> bool | None:
        return self._room.state.asleep if self._room.state else None
