"""Sensor platform for Daikin Comfort Control.

Provides the following sensors per device, all grouped under the same
device card in HA so they appear automatically on integration setup:

  - Outdoor Temperature       (deg C native, HA converts to user unit)
  - Indoor Temperature        (deg C native, HA converts to user unit)
  - Indoor Humidity           (%)
  - Fan Speed                 (string: auto / quiet / low / ...)
  - Fan Direction             (string: stopped / swing / position_N)
  - Compressor Frequency      (Hz, integer)
  - Compressor Power          (W relative, integer)
"""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfFrequency, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DAIKIN_TO_HA_FAN
from .coordinator import DaikinCoordinator

_LOGGER = logging.getLogger(__name__)

# f_dir_ud raw value -> friendly label
FAN_DIR_UD_MAP: dict[str, str] = {
    "0": "stopped",
    "1": "position_1",
    "2": "position_2",
    "3": "position_3",
    "4": "position_4",
    "5": "position_5",
    "S": "swing",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create all sensors for every discovered device."""
    coordinators: list[DaikinCoordinator] = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for coordinator in coordinators:
        entities += [
            DaikinOutdoorTempSensor(coordinator),
            DaikinIndoorTempSensor(coordinator),
            DaikinIndoorHumiditySensor(coordinator),
            DaikinFanSpeedSensor(coordinator),
            DaikinFanDirectionSensor(coordinator),
            DaikinCompressorFreqSensor(coordinator),
            DaikinCompressorPowerSensor(coordinator),
        ]
    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

class _DaikinBaseSensor(CoordinatorEntity[DaikinCoordinator], SensorEntity):
    """Shared base: attaches to the same DeviceInfo as the climate entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DaikinCoordinator, key: str) -> None:
        super().__init__(coordinator)
        device = coordinator.device
        self._attr_unique_id = f"{DOMAIN}_{device.uid}_{device.port}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.uid)},
            name=device.name,
            manufacturer="Daikin",
            model="BRP069C4x",
            sw_version=device.fw_ver.replace("_", "."),
        )

    @property
    def _state(self):
        return self.coordinator.data.state

    @property
    def _raw(self) -> dict[str, str]:
        return self.coordinator.data.raw_control


# ---------------------------------------------------------------------------
# Temperature sensors
# ---------------------------------------------------------------------------

class DaikinOutdoorTempSensor(_DaikinBaseSensor):
    _attr_name                       = "Outdoor Temperature"
    _attr_device_class               = SensorDeviceClass.TEMPERATURE
    _attr_state_class                = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon                       = "mdi:thermometer"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator, "outdoor_temp")

    @property
    def native_value(self) -> float | None:
        v = self._state.outdoor_temp
        return v if v != 0.0 else None


class DaikinIndoorTempSensor(_DaikinBaseSensor):
    _attr_name                       = "Indoor Temperature"
    _attr_device_class               = SensorDeviceClass.TEMPERATURE
    _attr_state_class                = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon                       = "mdi:thermometer"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator, "indoor_temp")

    @property
    def native_value(self) -> float | None:
        v = self._state.indoor_temp
        return v if v != 0.0 else None


# ---------------------------------------------------------------------------
# Humidity sensor
# ---------------------------------------------------------------------------

class DaikinIndoorHumiditySensor(_DaikinBaseSensor):
    _attr_name                       = "Indoor Humidity"
    _attr_device_class               = SensorDeviceClass.HUMIDITY
    _attr_state_class                = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon                       = "mdi:water-percent"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator, "indoor_humidity")

    @property
    def native_value(self) -> int | None:
        h = self._state.indoor_humidity
        return h if h > 0 else None


# ---------------------------------------------------------------------------
# Fan sensors
# ---------------------------------------------------------------------------

class DaikinFanSpeedSensor(_DaikinBaseSensor):
    _attr_name = "Fan Speed"
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator, "fan_speed")

    @property
    def native_value(self) -> str | None:
        raw_frate = self._raw.get("f_rate")
        if raw_frate is None:
            return None
        return DAIKIN_TO_HA_FAN.get(raw_frate, raw_frate)


class DaikinFanDirectionSensor(_DaikinBaseSensor):
    _attr_name = "Fan Direction"
    _attr_icon = "mdi:arrow-up-down"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator, "fan_dir_ud")

    @property
    def native_value(self) -> str | None:
        raw = self._raw.get("f_dir_ud")
        if raw is None:
            return None
        return FAN_DIR_UD_MAP.get(raw, f"position_{raw}")


# ---------------------------------------------------------------------------
# Compressor sensors
# ---------------------------------------------------------------------------

class DaikinCompressorFreqSensor(_DaikinBaseSensor):
    _attr_name                       = "Compressor Frequency"
    _attr_device_class               = SensorDeviceClass.FREQUENCY
    _attr_state_class                = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfFrequency.HERTZ
    _attr_icon                       = "mdi:sine-wave"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator, "cmpfreq")

    @property
    def native_value(self) -> int | None:
        v = self._state.cmpfreq
        return v if v > 0 else None


class DaikinCompressorPowerSensor(_DaikinBaseSensor):
    _attr_name                       = "Compressor Power"
    _attr_device_class               = SensorDeviceClass.POWER
    _attr_state_class                = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon                       = "mdi:lightning-bolt"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator, "mompow")

    @property
    def native_value(self) -> int | None:
        v = self._state.mompow
        return v if v > 0 else None
