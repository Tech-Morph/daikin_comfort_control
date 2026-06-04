"""Constants for Daikin Comfort Control."""

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

# Fan rate — 'A' = auto confirmed from capture (f_rate=A)
# Manual speeds 1-5 seen in dfr* fields (dfr1=4, dfr3=5 etc)
DAIKIN_FAN_AUTO   = "A"
DAIKIN_FAN_SPEEDS = ["1", "2", "3", "4", "5"]

# Swing — '0' = off confirmed from capture (f_dir_ud=0, f_dir_lr=0)
DAIKIN_SWING_OFF = "0"
DAIKIN_SWING_ON  = "1"
