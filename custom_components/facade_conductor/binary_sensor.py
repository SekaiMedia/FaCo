"""Je Raum: ob FaCo ihn gerade als schlafend behandelt, Aufstehpause eingerechnet."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FacadeConfigEntry
from .conductor import Conductor, Room
from .const import MODE_OFF
from .entity import RoomEntity, remove_stale


async def async_setup_entry(
    hass: HomeAssistant, entry: FacadeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    conductor = entry.runtime_data
    sensors = [AsleepSensor(conductor, room) for room in conductor.rooms if room.sleep_sensor]
    remove_stale(hass, entry.entry_id, "binary_sensor", sensors)
    for sensor in sensors:
        async_add_entities([sensor], config_subentry_id=sensor._room.subentry_id)


class AsleepSensor(RoomEntity, BinarySensorEntity):
    def __init__(self, conductor: Conductor, room: Room) -> None:
        super().__init__(conductor, room, "asleep")

    @property
    def available(self) -> bool:
        return self._conductor.mode != MODE_OFF and self._room.state is not None

    @property
    def is_on(self) -> bool | None:
        return self._room.state.asleep if self._room.state else None
