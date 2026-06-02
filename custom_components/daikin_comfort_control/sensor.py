"""Sensor platform for Daikin Comfort Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DaikinCoordinator

_LOGGER = logging.getLogger(__name__)

# f_dir_ud value → human label
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
    data = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for coordinator in data["coordinators"].values():
        entities.append(DaikinOutdoorTempSensor(coordinator))
        entities.append(DaikinFanDirectionSensor(coordinator))
    async_add_entities(entities)


class _DaikinBaseSensor(CoordinatorEntity[DaikinCoordinator], SensorEntity):
    """Shared base for Daikin sensors."""

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


class DaikinOutdoorTempSensor(_DaikinBaseSensor):
    """
    Outdoor temperature sensor.

    native_unit is CELSIUS (what the API returns). HA automatically
    converts to the user's configured unit system (°F if US).
    device_class=TEMPERATURE is what drives the conversion.
    """

    _attr_name               = "Outdoor Temperature"
    _attr_device_class       = SensorDeviceClass.TEMPERATURE
    _attr_state_class        = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator, "outdoor_temp")

    @property
    def native_value(self) -> float | None:
        otemp = self.coordinator.data.state.outdoor_temp
        return otemp if otemp != 0.0 else None


class DaikinFanDirectionSensor(_DaikinBaseSensor):
    """
    Up/down vane direction sensor.
    Reports the raw f_dir_ud value mapped to a human label.
    Will show 'unknown' until f_dir_ud value range is fully confirmed.
    """

    _attr_name = "Fan Direction"
    _attr_icon = "mdi:arrow-up-down"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator, "fan_dir_ud")

    @property
    def native_value(self) -> str | None:
        raw = self.coordinator.data.raw_control.get("f_dir_ud")
        if raw is None:
            return None
        return FAN_DIR_UD_MAP.get(raw, f"position_{raw}")
