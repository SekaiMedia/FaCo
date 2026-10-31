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
CONF_SAFETY = "safety"
CONF_NOTIFY_UNREACHABLE = "notify_unreachable"
CONF_NOTIFY_MANUAL = "notify_manual"
CONF_ANNOUNCE_UNREACHABLE = "announce_unreachable"
CONF_ANNOUNCE_MANUAL = "announce_manual"
# Haus: Lautsprecher für Räume ohne eigenen; Raum: eigener Lautsprecher
CONF_SPEAKER = "speaker"
CONF_GROUPS = "groups"
CONF_NOTIFY_SAFETY = "notify_safety"
CONF_ANNOUNCE_SAFETY = "announce_safety"
CONF_OUTDOOR_TEMP = "outdoor_temp"
CONF_RAIN_SENSOR = "rain_sensor"
CONF_RAIN_LEVEL = "rain_level"
CONF_OUTDOOR_HUMIDITY = "outdoor_humidity"
CONF_COLD_BELOW = "cold_below"
CONF_ALARM_PANEL = "alarm_panel"
# Ereignisse für Meldungen; je Ereignis notify_<e> für Push und announce_<e> für Durchsage
EVENTS = ["unreachable", "manual", "safety", "rain", "window", "alarm", "climate"]
RAIN_LEVEL_OPTIONS = ["light", "moderate", "heavy"]
CONF_WIND_DIRECTION = "wind_direction"
CONF_WIND_SPEED = "wind_speed"
CONF_WIND_GUST = "wind_gust"
CONF_WIND_LIMIT = "wind_limit"
CONF_SLAT_TILT = "slat_tilt"
CONF_VACATION_AFTER = "vacation_after"
CONF_NOTIFY_RAIN = "notify_rain"
CONF_ANNOUNCE_RAIN = "announce_rain"
GROUP_OPTIONS = ["house", "floor", "room"]

# Raum
CONF_AREA = "area"
CONF_COVERS = "covers"
CONF_WINDOW_SENSOR = "window_sensor"
# eigener Kippsensor zum Kontakt: dann heißt Kontakt offen ohne Kippen „ganz offen“
CONF_WINDOW_TILT = "window_tilt_sensor"
CONF_HUMIDITY_SENSOR = "humidity_sensor"
CONF_WALL_SENSOR = "wall_sensor"
# Anteil des Temperaturunterschieds an der kältesten Wandstelle, 0,7 nach DIN 4108-2
CONF_INSULATION = "insulation"
DEFAULT_INSULATION = 0.7
CONF_WINDOW_MEANS = "window_means"
# Tür mit Aussperrschutz; leer heißt: ja, wenn der Kontakt eine Tür ist
CONF_DOOR = "door"
CONF_SLEEP_SENSOR = "sleep_sensor"
CONF_SLEEP_PAUSE_START = "sleep_pause_start"
CONF_SLEEP_PAUSE_END = "sleep_pause_end"
CONF_SLEEP_WAKE_MINUTES = "sleep_wake_minutes"
CONF_SLEEP_WATTS = "sleep_watts"
CONF_COOLING_SENSOR = "cooling_sensor"
CONF_WAKE_SENSOR = "wake_sensor"
CONF_WAKE_LEAD = "wake_lead"
CONF_WAKE_WAIT = "wake_wait"
CONF_COOLING_ABOVE = "cooling_above"
CONF_COOLING_OUTSIDE = "cooling_outside"
# Eckzimmer: Gradzahl je Rollladen, sonst gilt die Richtung des Raums
CONF_COVER_DIRECTIONS = "cover_directions"
DEFAULT_COOLING_ABOVE = 24
DEFAULT_SLEEP_WATTS = 5
CONF_DIRECTION = "direction"
CONF_DIRECTION_DEG = "direction_deg"
CONF_SITUATIONS = "situations"
CONF_ADVANCED = "advanced"

POSITION_KEYS = ("day", "dusk", "night", "tilted", "open", "shade", "rain")
DEFAULT_POSITIONS = {"day": 100, "dusk": 25, "night": 0, "tilted": 25, "open": 100, "shade": 70, "rain": 10}

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
    CONF_SAFETY: [],
    CONF_NOTIFY_UNREACHABLE: True,
    CONF_NOTIFY_MANUAL: False,
    CONF_ANNOUNCE_UNREACHABLE: False,
    CONF_ANNOUNCE_MANUAL: False,
    CONF_SPEAKER: None,
    CONF_GROUPS: GROUP_OPTIONS,
    CONF_NOTIFY_SAFETY: False,
    CONF_ANNOUNCE_SAFETY: False,
    CONF_OUTDOOR_TEMP: None,
    CONF_RAIN_SENSOR: None,
    # gekippt erst ab mäßigem Regen; ganz offene Fenster schützen schon bei leichtem
    CONF_RAIN_LEVEL: "moderate",
    CONF_OUTDOOR_HUMIDITY: None,
    CONF_COLD_BELOW: 12,
    CONF_ALARM_PANEL: None,
    **{f"{kind}_{e}": False for kind in ("notify", "announce") for e in ("window", "alarm", "climate")},
    CONF_WIND_DIRECTION: None,
    CONF_WIND_SPEED: None,
    CONF_WIND_GUST: None,
    CONF_WIND_LIMIT: 50,
    CONF_SLAT_TILT: 50,
    # Stunden, nach denen ein leeres Haus als Urlaub gilt; 0 heißt nur per Schalter
    CONF_VACATION_AFTER: 0,
    CONF_NOTIFY_RAIN: False,
    CONF_ANNOUNCE_RAIN: False,
}

WINDOW_MEANS_OPTIONS = ["tilted", "open"]
# Geräteklassen, die als Fenster oder Tür zählen; das Panel nutzt dieselbe Liste
WINDOW_CLASSES = ["window", "door", "opening", "garage_door"]
DIRECTION_OPTIONS = ["none", "n", "ne", "e", "se", "s", "sw", "w", "nw"]

MODE_OFF = "off"
MODE_DRY_RUN = "dry_run"
MODE_AUTO = "auto"
MODES = [MODE_OFF, MODE_DRY_RUN, MODE_AUTO]

# Ereignisse der letzten Sekunden zu einer Entscheidung bündeln
BUNDLE_SECONDS = 2
EVALUATE_INTERVAL_SECONDS = 60
FORECAST_INTERVAL_MINUTES = 30
