"""Facade Conductor: Rollläden, Vorhänge und Fenster im Gleichlauf."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.start import async_at_started

from .conductor import Conductor

PLATFORMS = [Platform.SELECT, Platform.SENSOR]

type FacadeConfigEntry = ConfigEntry[Conductor]


async def async_setup_entry(hass: HomeAssistant, entry: FacadeConfigEntry) -> bool:
    conductor = Conductor(hass, entry)
    entry.runtime_data = conductor
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _start(_hass: HomeAssistant) -> None:
        await conductor.async_start()

    # erst loslegen, wenn alle Geräte geladen sind, sonst fehlen Positionen
    entry.async_on_unload(async_at_started(hass, _start))
    entry.async_on_unload(conductor.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FacadeConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: FacadeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
