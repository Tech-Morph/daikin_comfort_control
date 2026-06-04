"""Sensor platform for Daikin Comfort Control.

Sensors per device (all grouped under the same device card):
  - Indoor Temperature    (deg C native -> HA converts to user unit)
  - Outdoor Temperature   (deg C native -> HA converts to user unit)
  - Indoor Humidity       (%)
  - Fan Speed             (string)
  - Fan Direction         (string)
  - Compressor Frequency  (Hz)
  - Compressor Power      (W)
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
from .coordinator import DaikinCoordinator, DaikinDeviceData

_LOGGER = logging.getLogger(__name__)

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
    coordinators: list[DaikinCoordinator] = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for coordinator in coordinators:
        entities += [
            DaikinIndoorTempSensor(coordinator),
            DaikinOutdoorTempSensor(coordinator),
            DaikinIndoorHumiditySensor(coordinator),
            DaikinFanSpeedSensor(coordinator),
            DaikinFanDirectionSensor(coordinator),
            DaikinCompressorFreqSensor(coordinator),
            DaikinCompressorPowerSensor(coordinator),
        ]
    async_add_entities(entities)


class _DaikinBaseSensor(CoordinatorEntity[DaikinCoordinator], SensorEntity):
    """Shared base — attaches to the same DeviceInfo as the climate entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DaikinCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.device_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            name=coordinator.device_name,
            manufacturer="Daikin",
            model="BRP069C4x",
        )

    @property
    def _d(self) -> DaikinDeviceData:
        return self.coordinator.data


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
        v = self._d.indoor_temp
        return v if v != 0.0 else None


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
        v = self._d.outdoor_temp
        return v if v != 0.0 else None


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
        h = self._d.indoor_humidity
        return h if h > 0 else None


class DaikinFanSpeedSensor(_DaikinBaseSensor):
    _attr_name = "Fan Speed"
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator, "fan_speed")

    @property
    def native_value(self) -> str | None:
        return DAIKIN_TO_HA_FAN.get(self._d.fan_rate, self._d.fan_rate)


class DaikinFanDirectionSensor(_DaikinBaseSensor):
    _attr_name = "Fan Direction"
    _attr_icon = "mdi:arrow-up-down"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator, "fan_dir_ud")

    @property
    def native_value(self) -> str | None:
        return FAN_DIR_UD_MAP.get(self._d.f_dir_ud, f"position_{self._d.f_dir_ud}")


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
        v = self._d.cmpfreq
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
        v = self._d.mompow
        return v if v > 0 else None
