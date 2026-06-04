"""Constants for Daikin Comfort Control integration."""

DOMAIN = "daikin_comfort_control"

BASE_URL = "https://api.daikinskyport.com"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30

# API endpoints
ENDPOINT_AUTH = "/users/auth"
ENDPOINT_AUTH_REFRESH = "/users/auth/token"
ENDPOINT_DEVICES = "/devices"
ENDPOINT_DEVICE = "/devices/{device_id}"

# Daikin mode integers (confirm via mitmproxy capture)
DAIKIN_MODE_OFF = 0
DAIKIN_MODE_AUTO = 1
DAIKIN_MODE_DRY = 2
DAIKIN_MODE_COOL = 3
DAIKIN_MODE_HEAT = 4
DAIKIN_MODE_FAN = 6

DAIKIN_FAN_AUTO = "auto"
DAIKIN_FAN_QUIET = "quiet"
DAIKIN_FAN_LOW = "low"
DAIKIN_FAN_MEDIUM = "medium"
DAIKIN_FAN_HIGH = "high"
DAIKIN_FAN_POWERFUL = "powerful"

FAN_MODES = [
    DAIKIN_FAN_AUTO,
    DAIKIN_FAN_QUIET,
    DAIKIN_FAN_LOW,
    DAIKIN_FAN_MEDIUM,
    DAIKIN_FAN_HIGH,
    DAIKIN_FAN_POWERFUL,
]

MIN_TEMP = 16.0
MAX_TEMP = 30.0
TEMP_STEP = 0.5
