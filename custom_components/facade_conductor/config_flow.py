"""Einrichtung über die Oberfläche.

Erst kurz einrichten, alles Feinere später über „Konfigurieren“ als Menü. Das Haus ist der
Eintrag, jeder Raum ein Untereintrag. Was nicht eingestellt ist, nimmt die Vorgaben aus const.py.
"""

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
TIME = selector.TimeSelector()


def _number(minimum: float, maximum: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )


def _entity(domain: str | list[str], **kwargs: Any) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain, **kwargs))


def _select(options: list[str], key: str) -> selector.SelectSelector:
    return selector.SelectSelector(selector.SelectSelectorConfig(options=options, translation_key=key))


def _optional(key: str, values: dict[str, Any]) -> vol.Optional:
    """Optionales Feld mit Vorschlag, das sich wieder leeren lässt."""
    value = values.get(key)
    return vol.Optional(key, description={"suggested_value": value} if value is not None else None)


def _positions_schema(values: dict[str, Any], required: bool) -> vol.Schema:
    if required:
        merged = {**DEFAULT_POSITIONS, **values}
        return vol.Schema({vol.Required(k, default=merged[k]): PERCENT for k in POSITION_KEYS})
    # Raum: leer heißt Standard des Hauses
    return vol.Schema({_optional(k, values): PERCENT for k in POSITION_KEYS})


# Haus


class FacadeConductorConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Facade Conductor", data={CONF_WEATHER: user_input.get(CONF_WEATHER)})
        weather = next(iter(sorted(self.hass.states.async_entity_ids("weather"))), None)
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema({_optional(CONF_WEATHER, {CONF_WEATHER: weather}): _entity("weather")})
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HouseOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_ROOM: RoomSubentryFlow}


class HouseOptionsFlow(OptionsFlow):
    """Konfigurieren: ein Menü, jeder Punkt ändert nur seinen Teil."""

    def _current(self) -> dict[str, Any]:
        return {**DEFAULTS, **self.config_entry.data, **self.config_entry.options}

    def _save(self, changes: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **changes})

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["heat", "daylight", "night", "positions"])

    async def async_step_heat(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save({CONF_WEATHER: user_input.get(CONF_WEATHER), **user_input})
        v = self._current()
        schema = vol.Schema(
            {
                _optional(CONF_WEATHER, v): _entity("weather"),
                vol.Required(CONF_HOT_TEMPERATURE, default=v[CONF_HOT_TEMPERATURE]): _number(10, 40, 0.5, "°C"),
            }
        )
        return self.async_show_form(step_id="heat", data_schema=schema)

    async def async_step_daylight(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save({CONF_LUX_SENSOR: user_input.get(CONF_LUX_SENSOR), **user_input})
        v = self._current()
        schema = vol.Schema(
            {
                _optional(CONF_LUX_SENSOR, v): _entity("sensor", device_class="illuminance"),
                vol.Required(CONF_LUX_DARK, default=v[CONF_LUX_DARK]): _number(0, 100000, 50, "lx"),
                vol.Required(CONF_LUX_BRIGHT, default=v[CONF_LUX_BRIGHT]): _number(0, 100000, 50, "lx"),
            }
        )
        return self.async_show_form(step_id="daylight", data_schema=schema)

    async def async_step_night(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        v = self._current()
        schema = vol.Schema(
            {
                vol.Required(CONF_NIGHT_START, default=v[CONF_NIGHT_START]): TIME,
                vol.Required(CONF_NIGHT_END, default=v[CONF_NIGHT_END]): TIME,
                vol.Required(CONF_REST_MINUTES, default=v[CONF_REST_MINUTES]): _number(0, 240, 1, "min"),
            }
        )
        return self.async_show_form(step_id="night", data_schema=schema)

    async def async_step_positions(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save({CONF_POSITIONS: user_input})
        schema = _positions_schema(self._current().get(CONF_POSITIONS, {}), required=True)
        return self.async_show_form(step_id="positions", data_schema=schema)


# Raum


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


class RoomSubentryFlow(ConfigSubentryFlow):
    """Raum hinzufügen: Bereich wählen, Vorschläge bestätigen. Feineres über Konfigurieren."""

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
        name = area.name if area else self._area_id
        if user_input is not None:
            if not user_input.get(CONF_COVERS):
                errors[CONF_COVERS] = "no_covers"
            else:
                return self.async_create_entry(title=name, data={CONF_AREA: self._area_id, **user_input})
        values = user_input or {
            CONF_COVERS: _area_entities(self.hass, self._area_id, "cover"),
            CONF_WINDOW_SENSOR: next(
                iter(_area_entities(self.hass, self._area_id, "binary_sensor", {"window", "door", "opening"})), None
            ),
            CONF_DIRECTION: "none",
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_COVERS, default=values.get(CONF_COVERS, [])): _entity("cover", multiple=True),
                _optional(CONF_WINDOW_SENSOR, values): _entity("binary_sensor"),
                vol.Required(CONF_DIRECTION, default=values.get(CONF_DIRECTION, "none")): _select(
                    DIRECTION_OPTIONS, CONF_DIRECTION
                ),
            }
        )
        return self.async_show_form(
            step_id="room", data_schema=schema, errors=errors, description_placeholders={"area": name}
        )

    # Konfigurieren eines bestehenden Raums

    def _data(self) -> dict[str, Any]:
        return dict(self._get_reconfigure_subentry().data)

    def _update(self, changes: dict[str, Any]) -> SubentryFlowResult:
        return self.async_update_and_abort(self._get_entry(), self._get_reconfigure_subentry(), data_updates=changes)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return self.async_show_menu(
            step_id="reconfigure", menu_options=["devices", "window", "sun", "sleep", "own_positions"]
        )

    async def async_step_devices(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_COVERS):
                return self._update(user_input)
            errors[CONF_COVERS] = "no_covers"
        schema = vol.Schema(
            {vol.Required(CONF_COVERS, default=self._data().get(CONF_COVERS, [])): _entity("cover", multiple=True)}
        )
        return self.async_show_form(step_id="devices", data_schema=schema, errors=errors)

    async def async_step_window(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            return self._update({CONF_WINDOW_SENSOR: user_input.get(CONF_WINDOW_SENSOR), **user_input})
        v = self._data()
        schema = vol.Schema(
            {
                _optional(CONF_WINDOW_SENSOR, v): _entity("binary_sensor"),
                vol.Required(CONF_WINDOW_MEANS, default=v.get(CONF_WINDOW_MEANS, "tilted")): _select(
                    WINDOW_MEANS_OPTIONS, CONF_WINDOW_MEANS
                ),
            }
        )
        return self.async_show_form(step_id="window", data_schema=schema)

    async def async_step_sun(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            return self._update(user_input)
        schema = vol.Schema(
            {
                vol.Required(CONF_DIRECTION, default=self._data().get(CONF_DIRECTION, "none")): _select(
                    DIRECTION_OPTIONS, CONF_DIRECTION
                )
            }
        )
        return self.async_show_form(step_id="sun", data_schema=schema)

    async def async_step_sleep(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            pause = {k: user_input.get(k) for k in (CONF_SLEEP_PAUSE_START, CONF_SLEEP_PAUSE_END)}
            return self._update({CONF_SLEEP_SENSOR: user_input.get(CONF_SLEEP_SENSOR), CONF_ADVANCED: pause})
        v = self._data()
        pause = v.get(CONF_ADVANCED) or {}
        schema = vol.Schema(
            {
                _optional(CONF_SLEEP_SENSOR, v): _entity(["binary_sensor", "input_boolean"]),
                _optional(CONF_SLEEP_PAUSE_START, pause): TIME,
                _optional(CONF_SLEEP_PAUSE_END, pause): TIME,
            }
        )
        return self.async_show_form(step_id="sleep", data_schema=schema)

    async def async_step_own_positions(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            return self._update({CONF_POSITIONS: user_input})
        schema = _positions_schema(self._data().get(CONF_POSITIONS) or {}, required=False)
        return self.async_show_form(step_id="own_positions", data_schema=schema)
