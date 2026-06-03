"""Constants for Daikin Comfort Control."""
DOMAIN = "daikin_comfort_control"

# Daikin mode integer (as string) -> internal HA-friendly name
DAIKIN_MODE_MAP: dict[str, str] = {
    "1": "auto",
    "2": "dry",
    "3": "cool",
    "4": "heat",
    "6": "fan_only",
}
# Reverse: HA-friendly name -> Daikin mode integer string
DAIKIN_MODE_MAP_REVERSE: dict[str, str] = {v: k for k, v in DAIKIN_MODE_MAP.items()}

# Used by set_optimistic_data / coordinator to keep raw_control consistent
HA_TO_DAIKIN_MODE: dict[str, str] = DAIKIN_MODE_MAP_REVERSE

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
# Reverse: HA fan mode label -> Daikin f_rate raw value
HA_TO_DAIKIN_FAN: dict[str, str] = {v: k for k, v in DAIKIN_TO_HA_FAN.items()}
