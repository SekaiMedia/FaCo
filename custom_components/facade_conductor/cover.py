"""Gruppen zum Ansagen: ein Rollladen fürs Haus, je Etage und je Raum.

„Erdgeschoss runter“ fährt alle Räume der Etage im selben Takt. Wer über eine Gruppe fährt,
setzt die Räume in Handbetrieb, bis zur nächsten Tagesphase.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import ATTR_POSITION, CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FacadeConfigEntry
from .conductor import Conductor, Room, _position
from .const import DOMAIN
from .entity import RoomEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: FacadeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    conductor = entry.runtime_data
    rooms = [r for r in conductor.rooms if r.covers]
    areas = ar.async_get(hass)
    floors = fr.async_get(hass)

    groups: list[CoverEntity] = [HouseCover(conductor, rooms)]
    by_floor: dict[str, list[Room]] = {}
    for room in rooms:
        area = areas.async_get_area(room.area) if room.area else None
        if area and area.floor_id:
            by_floor.setdefault(area.floor_id, []).append(room)
    for floor_id, members in by_floor.items():
        if (floor := floors.async_get_floor(floor_id)) is not None:
            groups.append(FloorCover(conductor, members, floor_id, floor.name))
    async_add_entities(groups)

    dev_reg = dr.async_get(hass)
    for room in rooms:
        async_add_entities([RoomCover(conductor, room)], config_subentry_id=room.subentry_id)
        # Raumgruppen gehören in ihren Bereich, dann versteht Assist „Wohnzimmer runter“ ohne Zusatz
        device = dev_reg.async_get_device(identifiers={(DOMAIN, room.subentry_id)})
        if device and device.area_id is None and room.area:
            dev_reg.async_update_device(device.id, area_id=room.area)


class GroupMixin(CoverEntity):
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION
    _conductor: Conductor
    _members: list[Room]

    @property
    def current_cover_position(self) -> int | None:
        positions = [
            p for room in self._members for c in room.covers if (p := _position(self.hass.states.get(c))) is not None
        ]
        return round(sum(positions) / len(positions)) if positions else None

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        return None if position is None else position == 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._conductor.async_command(self._members, 100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._conductor.async_command(self._members, 0)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._conductor.async_command(self._members, int(kwargs[ATTR_POSITION]))


class HubCover(GroupMixin):
    """Gruppe am Hausgerät, aktualisiert sich mit jeder Entscheidung."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, conductor: Conductor, members: list[Room], key: str) -> None:
        self._conductor = conductor
        self._members = members
        self._attr_unique_id = f"{conductor.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, conductor.entry.entry_id)},
            name="Facade Conductor",
            manufacturer="SekaiMedia",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._conductor.add_listener(self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()


class HouseCover(HubCover):
    _attr_translation_key = "all_covers"

    def __init__(self, conductor: Conductor, members: list[Room]) -> None:
        super().__init__(conductor, members, "all_covers")


class FloorCover(HubCover):
    _attr_translation_key = "floor_covers"

    def __init__(self, conductor: Conductor, members: list[Room], floor_id: str, floor_name: str) -> None:
        super().__init__(conductor, members, f"floor_{floor_id}")
        self._attr_translation_placeholders = {"floor": floor_name}


class RoomCover(RoomEntity, GroupMixin):
    def __init__(self, conductor: Conductor, room: Room) -> None:
        super().__init__(conductor, room, "room_covers")
        self._members = [room]

    @property
    def available(self) -> bool:
        return True
