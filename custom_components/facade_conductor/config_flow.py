"""Einrichtung über die Oberfläche: das Haus als Eintrag, jeder Raum als Untereintrag."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_ADVANCED,
    CONF_AREA,
    CONF_COVERS,
    CONF_DIRECTION,
    CONF_HOT_TEMPERATURE,
    CONF_LUX_BRIGHT,
    CONF_LUX_DARK,
    CONF_LUX_SENSOR,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_POSITIONS,
    CONF_REST_MINUTES,
    CONF_SLEEP_PAUSE_END,
    CONF_SLEEP_PAUSE_START,
    CONF_SLEEP_SENSOR,
    CONF_WEATHER,
    CONF_WINDOW_MEANS,
    CONF_WINDOW_SENSOR,
    DEFAULT_POSITIONS,
    DEFAULTS,
    DIRECTION_OPTIONS,
    DOMAIN,
    POSITION_KEYS,
    SUBENTRY_ROOM,
    WINDOW_MEANS_OPTIONS,
)

PERCENT = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX)
)


def _number(minimum: float, maximum: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )


def _suggest(values: dict[str, Any], key: str) -> dict[str, Any]:
    return {"suggested_value": values.get(key)} if values.get(key) is not None else {}


def house_schema(values: dict[str, Any]) -> vol.Schema:
    v = {**DEFAULTS, **values}
    positions = {**DEFAULT_POSITIONS, **values.get(CONF_POSITIONS, {})}
    return vol.Schema(
        {
            vol.Optional(CONF_WEATHER, description=_suggest(v, CONF_WEATHER)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Required(CONF_HOT_TEMPERATURE, default=v[CONF_HOT_TEMPERATURE]): _number(10, 40, 0.5, "°C"),
            vol.Optional(CONF_LUX_SENSOR, description=_suggest(v, CONF_LUX_SENSOR)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="illuminance")
            ),
            vol.Required(CONF_LUX_DARK, default=v[CONF_LUX_DARK]): _number(0, 100000, 50, "lx"),
            vol.Required(CONF_LUX_BRIGHT, default=v[CONF_LUX_BRIGHT]): _number(0, 100000, 50, "lx"),
            vol.Required(CONF_NIGHT_START, default=v[CONF_NIGHT_START]): selector.TimeSelector(),
            vol.Required(CONF_NIGHT_END, default=v[CONF_NIGHT_END]): selector.TimeSelector(),
            vol.Required(CONF_REST_MINUTES, default=v[CONF_REST_MINUTES]): _number(0, 240, 1, "min"),
            vol.Required(CONF_POSITIONS): section(
                vol.Schema({vol.Required(k, default=positions[k]): PERCENT for k in POSITION_KEYS}),
                {"collapsed": True},
            ),
        }
    )


class FacadeConductorConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Facade Conductor", data=user_input)
        return self.async_show_form(step_id="user", data_schema=house_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HouseOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_ROOM: RoomSubentryFlow}


class HouseOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=house_schema(current))


def _area_entities(hass: HomeAssistant, area_id: str, domain: str, device_classes: set[str] | None = None) -> list[str]:
    """Entitäten im Bereich, auch über das Gerät zugeordnete. Gruppen zählen nicht doppelt."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    found = []
    for entry in ent_reg.entities.values():
        if entry.domain != domain or entry.disabled or entry.platform == "group":
            continue
        area = entry.area_id
        if area is None and entry.device_id and (device := dev_reg.async_get(entry.device_id)):
            area = device.area_id
        if area != area_id:
            continue
        if device_classes and (entry.device_class or entry.original_device_class) not in device_classes:
            continue
        found.append(entry.entity_id)
    return sorted(found)


def room_schema(values: dict[str, Any]) -> vol.Schema:
    positions = values.get(CONF_POSITIONS, {})
    advanced = values.get(CONF_ADVANCED, {})
    return vol.Schema(
        {
            vol.Required(CONF_COVERS, default=values.get(CONF_COVERS, [])): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="cover", multiple=True)
            ),
            vol.Optional(CONF_WINDOW_SENSOR, description=_suggest(values, CONF_WINDOW_SENSOR)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Required(CONF_WINDOW_MEANS, default=values.get(CONF_WINDOW_MEANS, "tilted")): selector.SelectSelector(
                selector.SelectSelectorConfig(options=WINDOW_MEANS_OPTIONS, translation_key=CONF_WINDOW_MEANS)
            ),
            vol.Required(CONF_DIRECTION, default=values.get(CONF_DIRECTION, "none")): selector.SelectSelector(
                selector.SelectSelectorConfig(options=DIRECTION_OPTIONS, translation_key=CONF_DIRECTION)
            ),
            vol.Optional(CONF_SLEEP_SENSOR, description=_suggest(values, CONF_SLEEP_SENSOR)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])
            ),
            # leer = Standard des Hauses
            vol.Required(CONF_POSITIONS): section(
                vol.Schema({vol.Optional(k, description=_suggest(positions, k)): PERCENT for k in POSITION_KEYS}),
                {"collapsed": True},
            ),
            vol.Required(CONF_ADVANCED): section(
                vol.Schema(
                    {
                        vol.Optional(
                            CONF_SLEEP_PAUSE_START, description=_suggest(advanced, CONF_SLEEP_PAUSE_START)
                        ): selector.TimeSelector(),
                        vol.Optional(
                            CONF_SLEEP_PAUSE_END, description=_suggest(advanced, CONF_SLEEP_PAUSE_END)
                        ): selector.TimeSelector(),
                    }
                ),
                {"collapsed": True},
            ),
        }
    )


class RoomSubentryFlow(ConfigSubentryFlow):
    """Raum anlegen: erst den Bereich wählen, dann vorgeschlagene Geräte prüfen."""

    _area_id: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            self._area_id = user_input[CONF_AREA]
            return await self.async_step_room()
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema({vol.Required(CONF_AREA): selector.AreaSelector()})
        )

    async def async_step_room(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        area = ar.async_get(self.hass).async_get_area(self._area_id)
        if user_input is not None:
            if not user_input[CONF_COVERS]:
                errors[CONF_COVERS] = "no_covers"
            else:
                data = {CONF_AREA: self._area_id, **user_input}
                return self.async_create_entry(title=area.name if area else self._area_id, data=data)
        suggested = {
            CONF_COVERS: _area_entities(self.hass, self._area_id, "cover"),
            CONF_WINDOW_SENSOR: next(
                iter(_area_entities(self.hass, self._area_id, "binary_sensor", {"window", "door", "opening"})), None
            ),
        }
        return self.async_show_form(
            step_id="room",
            data_schema=room_schema(user_input or suggested),
            errors=errors,
            description_placeholders={"area": area.name if area else ""},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, data={CONF_AREA: subentry.data[CONF_AREA], **user_input}
            )
        return self.async_show_form(step_id="reconfigure", data_schema=room_schema(dict(subentry.data)))
