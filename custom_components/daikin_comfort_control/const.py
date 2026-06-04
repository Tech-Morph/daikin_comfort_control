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

# Polling interval
DEFAULT_SCAN_INTERVAL = 30  # seconds

# HVAC mode integers — confirmed: mode=3 is COOL from mitmproxy capture
DAIKIN_MODE_AUTO = 1
DAIKIN_MODE_DRY  = 2
DAIKIN_MODE_COOL = 3
DAIKIN_MODE_HEAT = 4
DAIKIN_MODE_FAN  = 6

# Fan rate — 'A' = auto confirmed from capture (f_rate=A in set_control_info)
# f_rate values seen: A=auto, 1=quiet, 2=low, 3=medium, 4=high, 5=powerful
# Maps between Daikin f_rate string and HA fan mode string
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
# Daikin BRP069C4x range: 60–86°F (confirmed: hmlmt_l=10.0°C in model info)
MIN_TEMP_F  = 60.0
MAX_TEMP_F  = 86.0
TEMP_STEP_F = 1.0
