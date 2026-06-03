"""Constants for Daikin Comfort Control.

This is the single source of truth for every name imported from .const
across the integration. Before editing, check every import in:
  __init__.py, daikin_api.py, coordinator.py, climate.py, sensor.py
"""
DOMAIN = "daikin_comfort_control"

# ---------------------------------------------------------------------------
# Config entry keys
# ---------------------------------------------------------------------------
CONF_USERNAME        = "username"
CONF_PASSWORD        = "password"
CONF_UID             = "uid"
CONF_SCAN_INTERVAL   = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30

# ---------------------------------------------------------------------------
# Mode mappings
# ---------------------------------------------------------------------------
DAIKIN_TO_HA_MODE: dict[int, str] = {
    1: "auto",
    2: "dry",
    3: "cool",
    4: "heat",
    6: "fan_only",
}
HA_TO_DAIKIN_MODE: dict[str, int] = {v: k for k, v in DAIKIN_TO_HA_MODE.items()}

# ---------------------------------------------------------------------------
# Fan speed mappings
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Swing mode mappings
#
# Confirmed via mitmproxy (2026-06-03):
#   dfd3=0  f_dir_ud=0  f_dir_lr=0  -> swing off
#   dfd3=1  f_dir_ud=S  f_dir_lr=0  -> tilt (up/down swing)
#   dfd3=2  f_dir_ud=0  f_dir_lr=S  -> horizontal (left/right swing)
#   dfd3=3  f_dir_ud=S  f_dir_lr=S  -> both / 3D swing
#
# All three params must be sent together on every set_control call.
# HA swing mode label -> (dfd3, f_dir_ud, f_dir_lr)
# ---------------------------------------------------------------------------
SWING_OFF        = "off"
SWING_TILT       = "vertical"     # HA built-in label for up/down
SWING_HORIZONTAL = "horizontal"   # HA built-in label for left/right
SWING_BOTH       = "both"         # HA built-in label for 3D

# HA swing label -> (dfd3 str, f_dir_ud str, f_dir_lr str)
HA_TO_DAIKIN_SWING: dict[str, tuple[str, str, str]] = {
    SWING_OFF:        ("0", "0", "0"),
    SWING_TILT:       ("1", "S", "0"),
    SWING_HORIZONTAL: ("2", "0", "S"),
    SWING_BOTH:       ("3", "S", "S"),
}

# (dfd3 str) -> HA swing label
DAIKIN_TO_HA_SWING: dict[str, str] = {
    "0": SWING_OFF,
    "1": SWING_TILT,
    "2": SWING_HORIZONTAL,
    "3": SWING_BOTH,
}

# ---------------------------------------------------------------------------
# Mode-specific temperature sentinels
# ---------------------------------------------------------------------------
MODE_STEMP_SENTINEL: dict[str, str] = {
    "dry":      "M",
    "fan_only": "--",
}

# ---------------------------------------------------------------------------
# Mode-specific temperature parameter names
# ---------------------------------------------------------------------------
MODE_TEMP_PARAMS: dict[int, tuple[str, str]] = {
    1: ("dt1", "dh1"),
    2: ("dt2", "dh2"),
    3: ("dt3", "dh3"),
    4: ("dt4", "dh4"),
    6: ("dt6", "dh6"),
}
