"""Constants for Daikin Comfort Control."""

from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
)

DOMAIN = "daikin_comfort_control"

# Cloud API base URL (confirmed via mitmproxy)
BASE_URL = "https://scr.daikincloud.net"

# Config entry keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_UID      = "uid"

# Device UID captured via mitmproxy — must match the value registered
# with Daikin cloud or device_list returns empty.
DEFAULT_UID = "dcd2e719644c4716afc1f729e98b609c"

# Polling interval
DEFAULT_SCAN_INTERVAL = 30  # seconds

# HVAC mode integers — confirmed: mode=3 is COOL from mitmproxy capture
DAIKIN_MODE_AUTO = 1
DAIKIN_MODE_DRY  = 2
DAIKIN_MODE_COOL = 3
DAIKIN_MODE_HEAT = 4
DAIKIN_MODE_FAN  = 6

# Fan rate — 'A' = auto confirmed from capture (f_rate=A in set_control_info)
DAIKIN_FAN_AUTO = "A"

DAIKIN_TO_HA_FAN: dict[str, str] = {
    "A": FAN_AUTO,
    "1": "quiet",
    "2": FAN_LOW,
    "3": FAN_MEDIUM,
    "4": FAN_HIGH,
    "5": "powerful",
}

HA_TO_DAIKIN_FAN: dict[str, str] = {v: k for k, v in DAIKIN_TO_HA_FAN.items()}

# Swing — '0' = off confirmed from capture (f_dir_ud=0, f_dir_lr=0)
DAIKIN_SWING_OFF = "0"
DAIKIN_SWING_ON  = "1"

# Temperature limits (Fahrenheit — the app displays in °F for US/reg=us)
MIN_TEMP_F  = 64.0
MAX_TEMP_F  = 90.0
TEMP_STEP_F = 1.0
