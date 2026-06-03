"""Constants for Daikin Comfort Control.

This is the single source of truth for every name imported from .const
across the integration. Before editing, check every import in:
  __init__.py, daikin_api.py, coordinator.py, climate.py, sensor.py
"""
DOMAIN = "daikin_comfort_control"

# ---------------------------------------------------------------------------
# Config entry keys  (used by __init__.py and config_flow.py)
# ---------------------------------------------------------------------------
CONF_USERNAME        = "username"
CONF_PASSWORD        = "password"
CONF_UID             = "uid"
CONF_SCAN_INTERVAL   = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30

# ---------------------------------------------------------------------------
# Mode mappings
# Daikin uses integer strings; internally we use HA-friendly names.
# ---------------------------------------------------------------------------

# Daikin mode integer (as int) -> HA-friendly name
DAIKIN_TO_HA_MODE: dict[int, str] = {
    1: "auto",
    2: "dry",
    3: "cool",
    4: "heat",
    6: "fan_only",
}

# HA-friendly name -> Daikin mode integer (as int)
HA_TO_DAIKIN_MODE: dict[str, int] = {v: k for k, v in DAIKIN_TO_HA_MODE.items()}

# ---------------------------------------------------------------------------
# Fan speed mappings
# Daikin uses single-char / digit codes; HA uses descriptive strings.
# ---------------------------------------------------------------------------

# Daikin f_rate raw value -> HA fan mode label
DAIKIN_TO_HA_FAN: dict[str, str] = {
    "A": "auto",
    "B": "quiet",
    "3": "low",
    "4": "medium_low",
    "5": "medium",
    "6": "medium_high",
    "7": "high",
}

# HA fan mode label -> Daikin f_rate raw value
HA_TO_DAIKIN_FAN: dict[str, str] = {v: k for k, v in DAIKIN_TO_HA_FAN.items()}

# ---------------------------------------------------------------------------
# Mode-specific temperature sentinels
# Some modes send a non-numeric stemp value instead of a real temperature.
# ---------------------------------------------------------------------------

# HA mode name -> stemp value to send when mode has no real setpoint
MODE_STEMP_SENTINEL: dict[str, str] = {
    "dry":      "M",   # Daikin dry mode uses 'M' as stemp
    "fan_only": "--",  # Fan-only mode uses '--' as stemp
}

# ---------------------------------------------------------------------------
# Mode-specific temperature parameter names
# Each mode stores its own last-used setpoint in dtN / dhN params.
# Key: Daikin mode integer; Value: (dt_param, dh_param)
# ---------------------------------------------------------------------------
MODE_TEMP_PARAMS: dict[int, tuple[str, str]] = {
    1: ("dt1", "dh1"),  # auto
    2: ("dt2", "dh2"),  # dry
    3: ("dt3", "dh3"),  # cool
    4: ("dt4", "dh4"),  # heat
    6: ("dt6", "dh6"),  # fan_only
}
