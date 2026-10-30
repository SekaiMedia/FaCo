"""Betriebsart fürs ganze Haus: Aus, Probelauf oder Automatik."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import FacadeConfigEntry
from .const import DOMAIN, MODE_DRY_RUN, MODES


async def async_setup_entry(
    hass: HomeAssistant, entry: FacadeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([ModeSelect(entry)])


class ModeSelect(SelectEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "mode"
    _attr_options = MODES

    def __init__(self, entry: FacadeConfigEntry) -> None:
        self._conductor = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_mode"
        self._attr_current_option = MODE_DRY_RUN
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Facade Conductor",
            manufacturer="SekaiMedia",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        # Neu eingerichtet beginnt alles im Probelauf: rechnen und anzeigen, nicht fahren
        if (last := await self.async_get_last_state()) and last.state in MODES:
            self._attr_current_option = last.state
        self._conductor.set_mode(self._attr_current_option)

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self._conductor.set_mode(option)
        self.async_write_ha_state()
