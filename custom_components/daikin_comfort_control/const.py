"""Constants for Daikin Comfort Control integration.

Values confirmed via mitmproxy traffic capture 2026-06-02 where noted.
Base URL: https://scr.daikincloud.net
"""

DOMAIN = "daikin_comfort_control"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_UID = "uid"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30

# mode= values confirmed/inferred from capture
HA_TO_DAIKIN_MODE: dict[str, int] = {
    "auto": 1,        # still inferred
    "dry": 2,         # still inferred
    "cool": 3,        # confirmed
    "heat": 4,        # confirmed
    "fan_only": 6,    # still inferred
}
DAIKIN_TO_HA_MODE: dict[int, str] = {v: k for k, v in HA_TO_DAIKIN_MODE.items()}

# f_rate values confirmed/inferred from capture
HA_TO_DAIKIN_FAN: dict[str, str] = {
    "auto": "A",          # confirmed
    "quiet": "B",         # inferred
    "night": "B",         # inferred alias
    "low": "3",           # inferred
    "medium_low": "4",    # confirmed in heat request
    "medium": "5",        # inferred
    "medium_high": "6",   # inferred
    "high": "7",          # inferred
    "powerful": "7",      # inferred alias
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

MODE_STEMP_SENTINEL: dict[str, str] = {
    "dry": "M",
    "fan_only": "--",
}

# Mode-specific dt/dh parameters confirmed for cool=3 and heat=4.
MODE_TEMP_PARAMS: dict[int, tuple[str, str]] = {
    1: ("dt1", "dh1"),
    2: ("dt2", "dh2"),
    3: ("dt3", "dh3"),
    4: ("dt4", "dh4"),
    6: ("dt6", "dh6"),
}
