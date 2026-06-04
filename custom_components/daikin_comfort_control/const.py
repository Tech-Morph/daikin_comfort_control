"""Constants for Daikin Comfort Control integration."""

DOMAIN = "daikin_comfort_control"

# Confirmed via mitmproxy capture
BASE_URL = "https://scr.daikincloud.net"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_UID      = "uid"          # x-daikin-uid header value (app device fingerprint)
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30

# API endpoints (all confirmed via mitmproxy)
ENDPOINT_AUTH        = "/common/login"
ENDPOINT_AUTH_REFRESH = "/common/refresh-token"
ENDPOINT_DEVICES     = "/common/device_list"
ENDPOINT_GET_CONTROL = "/aircon/get_control_info"
ENDPOINT_SET_CONTROL = "/aircon/set_control_info"

# Daikin mode integers (confirmed: mode=3 is Cool)
DAIKIN_MODE_AUTO = 1
DAIKIN_MODE_DRY  = 2
DAIKIN_MODE_COOL = 3
DAIKIN_MODE_HEAT = 4
DAIKIN_MODE_FAN  = 6

# Fan rate raw values <-> HA fan mode strings
# Confirmed: f_rate=A is auto
DAIKIN_TO_HA_FAN: dict[str, str] = {
    "A": "auto",
    "B": "quiet",
    "3": "low",
    "4": "medium_low",
    "5": "medium",
    "6": "medium_high",
    "7": "high",
}
HA_TO_DAIKIN_FAN: dict[str, str] = {v: k for k, v in DAIKIN_TO_HA_FAN.items()}

MIN_TEMP_F  = 64.0
MAX_TEMP_F  = 86.0
TEMP_STEP_F = 1.0
