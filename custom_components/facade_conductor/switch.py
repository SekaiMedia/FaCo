"""Je Raum: Handbetrieb sehen und beenden, auch aus Automationen heraus."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FacadeConfigEntry
from .conductor import Conductor, Room
from .const import MODE_AUTO
from .entity import RoomEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: FacadeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    conductor = entry.runtime_data
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
