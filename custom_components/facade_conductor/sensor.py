"""Je Raum: warum der Rollladen so steht, wohin er soll und wie FaCo das Fenster sieht."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FacadeConfigEntry
from .conductor import Conductor, Room
from .const import MODE_OFF
from .engine import Reason, Window
from .entity import RoomEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: FacadeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    conductor = entry.runtime_data
    for room in conductor.rooms:
        entities = [ReasonSensor(conductor, room), TargetSensor(conductor, room)]
        if room.window_sensor:
            entities.append(WindowSensor(conductor, room))
        async_add_entities(entities, config_subentry_id=room.subentry_id)


class ReasonSensor(RoomEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [r.value for r in Reason]

    def __init__(self, conductor: Conductor, room: Room) -> None:
        super().__init__(conductor, room, "reason")

    @property
    def native_value(self) -> str | None:
        return self._room.decision.reason.value if self._room.decision else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._room.decision:
            return None
        attrs: dict[str, Any] = {"level": self._room.decision.level}
        if self._room.decision.reason is Reason.SITUATION:
            attrs["situation"] = self._room.situation
        return attrs


class TargetSensor(RoomEntity, SensorEntity):
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, conductor: Conductor, room: Room) -> None:
        super().__init__(conductor, room, "target_position")

    @property
    def native_value(self) -> int | None:
        return self._room.decision.position if self._room.decision else None


class WindowSensor(RoomEntity, SensorEntity):
    """Das Fenster, wie es in die Entscheidung eingeht: ein offener Kontakt kann „gekippt“ bedeuten."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [w.name.lower() for w in Window]

    def __init__(self, conductor: Conductor, room: Room) -> None:
        super().__init__(conductor, room, "window")

    @property
    def available(self) -> bool:
        return self._conductor.mode != MODE_OFF and self._room.state is not None

    @property
    def native_value(self) -> str | None:
        return self._room.state.window.name.lower() if self._room.state else None
