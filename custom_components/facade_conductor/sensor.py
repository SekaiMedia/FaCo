"""Je Raum: warum der Rollladen so steht und wohin er soll."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FacadeConfigEntry
from .conductor import Conductor, Room
from .const import DOMAIN, MODE_OFF
from .engine import Reason


async def async_setup_entry(
    hass: HomeAssistant, entry: FacadeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    conductor = entry.runtime_data
    for room in conductor.rooms:
        async_add_entities(
            [ReasonSensor(conductor, room), TargetSensor(conductor, room)],
            config_subentry_id=room.subentry_id,
        )


class RoomEntity(SensorEntity):
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


class ReasonSensor(RoomEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [r.value for r in Reason]

    def __init__(self, conductor: Conductor, room: Room) -> None:
        super().__init__(conductor, room, "reason")

    @property
    def native_value(self) -> str | None:
        return self._room.decision.reason.value if self._room.decision else None

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        if not self._room.decision:
            return None
        return {"level": self._room.decision.level}


class TargetSensor(RoomEntity):
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, conductor: Conductor, room: Room) -> None:
        super().__init__(conductor, room, "target_position")

    @property
    def native_value(self) -> int | None:
        return self._room.decision.position if self._room.decision else None
