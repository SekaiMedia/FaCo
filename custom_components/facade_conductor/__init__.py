"""Facade Conductor: Rollläden, Vorhänge und Fenster im Gleichlauf."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.frontend import DATA_PANELS, async_remove_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from . import websocket
from .conductor import Conductor
from .const import DOMAIN

PLATFORMS = [Platform.BINARY_SENSOR, Platform.COVER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PANEL_URL = "facade-conductor"
STATIC_URL = f"/{DOMAIN}_static"

type FacadeConfigEntry = ConfigEntry[Conductor]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False)]
    )
    websocket.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FacadeConfigEntry) -> bool:
    conductor = Conductor(hass, entry)
    entry.runtime_data = conductor
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Jedes Speichern lädt den Eintrag neu. Die Seite bleibt dabei stehen, sonst springt der Browser weg.
    if PANEL_URL not in hass.data.get(DATA_PANELS, {}):
        version = (await async_get_integration(hass, DOMAIN)).version
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name="facade-conductor-panel",
            sidebar_title="Facade Conductor",
            sidebar_icon="mdi:window-shutter",
            module_url=f"{STATIC_URL}/panel.js?v={version}",
            require_admin=True,
            config={"version": version},
        )

    async def _start(_hass: HomeAssistant) -> None:
        await conductor.async_start()

    # erst loslegen, wenn alle Geräte geladen sind, sonst fehlen Positionen
    entry.async_on_unload(async_at_started(hass, _start))
    entry.async_on_unload(conductor.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FacadeConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: FacadeConfigEntry) -> None:
    if PANEL_URL in hass.data.get(DATA_PANELS, {}):
        async_remove_panel(hass, PANEL_URL)


async def _async_reload(hass: HomeAssistant, entry: FacadeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
