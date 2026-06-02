"""Constants for Daikin Comfort Control integration.

All values fully confirmed via mitmproxy traffic capture 2026-06-02.
Base URL: https://scr.daikincloud.net
"""

DOMAIN = "daikin_comfort_control"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_UID = "uid"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30

# All mode values confirmed via traffic capture 2026-06-02
HA_TO_DAIKIN_MODE: dict[str, int] = {
    "auto":     1,
    "dry":      2,
    "cool":     3,
    "heat":     4,
    "fan_only": 6,
}
DAIKIN_TO_HA_MODE: dict[int, str] = {v: k for k, v in HA_TO_DAIKIN_MODE.items()}

# All f_rate values confirmed via traffic capture 2026-06-02
HA_TO_DAIKIN_FAN: dict[str, str] = {
    "auto":        "A",
    "quiet":       "B",
    "night":       "B",
    "low":         "3",
    "medium_low":  "4",
    "medium":      "5",
    "medium_high": "6",
    "high":        "7",
    "powerful":    "7",
}
DAIKIN_TO_HA_FAN: dict[str, str] = {
    "A": "auto",
    "B": "quiet",
    "3": "low",
    "4": "medium_low",
    "5": "medium",
    "6": "medium_high",
    "7": "high",
}

# stemp sentinels for modes that don't use a numeric setpoint
MODE_STEMP_SENTINEL: dict[str, str] = {
    "dry":      "M",
    "fan_only": "--",
}

# Mode-specific dt/dh parameter names - all confirmed via capture
MODE_TEMP_PARAMS: dict[int, tuple[str, str]] = {
    1: ("dt1", "dh1"),
    2: ("dt2", "dh2"),
    3: ("dt3", "dh3"),
    4: ("dt4", "dh4"),
    6: ("dt6", "dh6"),
}
