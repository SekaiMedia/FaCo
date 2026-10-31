"""Konstanten für Facade Conductor."""

DOMAIN = "facade_conductor"
SUBENTRY_ROOM = "room"

# Haus
CONF_WEATHER = "weather"
CONF_HOT_TEMPERATURE = "hot_temperature"
CONF_LUX_SENSOR = "lux_sensor"
CONF_LUX_DARK = "lux_dark"
CONF_LUX_BRIGHT = "lux_bright"
CONF_NIGHT_START = "night_start"
CONF_NIGHT_END = "night_end"
CONF_REST_MINUTES = "rest_minutes"
CONF_POSITIONS = "positions"
CONF_LEAVE_ENABLED = "leave_enabled"
CONF_LEAVE_CONTACTS = "leave_contacts"
CONF_LEAVE_EXCLUDE_PERSONS = "leave_exclude_persons"

# Raum
CONF_AREA = "area"
CONF_COVERS = "covers"
CONF_WINDOW_SENSOR = "window_sensor"
CONF_WINDOW_MEANS = "window_means"
CONF_SLEEP_SENSOR = "sleep_sensor"
CONF_SLEEP_PAUSE_START = "sleep_pause_start"
CONF_SLEEP_PAUSE_END = "sleep_pause_end"
CONF_SLEEP_WAKE_MINUTES = "sleep_wake_minutes"
CONF_SLEEP_WATTS = "sleep_watts"
DEFAULT_SLEEP_WATTS = 5
CONF_DIRECTION = "direction"
CONF_ADVANCED = "advanced"

POSITION_KEYS = ("day", "dusk", "night", "tilted", "open", "shade")
DEFAULT_POSITIONS = {"day": 100, "dusk": 25, "night": 0, "tilted": 25, "open": 100, "shade": 70}

DEFAULTS = {
    CONF_HOT_TEMPERATURE: 23,
    CONF_LUX_DARK: 2500,
    CONF_LUX_BRIGHT: 4000,
    CONF_NIGHT_START: "23:00:00",
    CONF_NIGHT_END: "07:00:00",
    CONF_REST_MINUTES: 20,
    CONF_LEAVE_ENABLED: True,
    # Innentüren sollen nicht melden, deshalb wählt man die Kontakte selbst
    CONF_LEAVE_CONTACTS: [],
    CONF_LEAVE_EXCLUDE_PERSONS: [],
}

WINDOW_MEANS_OPTIONS = ["tilted", "open"]
DIRECTION_OPTIONS = ["none", "n", "ne", "e", "se", "s", "sw", "w", "nw"]

MODE_OFF = "off"
MODE_DRY_RUN = "dry_run"
MODE_AUTO = "auto"
MODES = [MODE_OFF, MODE_DRY_RUN, MODE_AUTO]

# Ereignisse der letzten Sekunden zu einer Entscheidung bündeln
BUNDLE_SECONDS = 2
EVALUATE_INTERVAL_SECONDS = 60
FORECAST_INTERVAL_MINUTES = 30
