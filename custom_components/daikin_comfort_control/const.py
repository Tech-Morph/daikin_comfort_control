DOMAIN = "daikin_comfort_control"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_UID      = "uid"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30

# Daikin mode numbers
DAIKIN_MODE_AUTO     = 1
DAIKIN_MODE_DRY      = 2
DAIKIN_MODE_COOL     = 3
DAIKIN_MODE_HEAT     = 4
DAIKIN_MODE_FAN_ONLY = 6

HA_TO_DAIKIN_MODE = {
    "auto":     DAIKIN_MODE_AUTO,
    "dry":      DAIKIN_MODE_DRY,
    "cool":     DAIKIN_MODE_COOL,
    "heat":     DAIKIN_MODE_HEAT,
    "fan_only": DAIKIN_MODE_FAN_ONLY,
}
DAIKIN_TO_HA_MODE = {v: k for k, v in HA_TO_DAIKIN_MODE.items()}

HA_TO_DAIKIN_FAN = {
    "auto":        "A",
    "night":       "B",
    "quiet":       "6",
    "low":         "1",
    "medium_low":  "2",
    "medium":      "3",
    "medium_high": "4",
    "high":        "5",
    "powerful":    "7",
}
DAIKIN_TO_HA_FAN = {v: k for k, v in HA_TO_DAIKIN_FAN.items()}
