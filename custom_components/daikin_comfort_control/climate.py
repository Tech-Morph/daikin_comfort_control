from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    HA_TO_DAIKIN_FAN, DAIKIN_TO_HA_FAN,
    HA_TO_DAIKIN_MODE,
)
from .coordinator import DaikinCoordinator
from .daikin_api import DaikinDevice

_LOGGER = logging.getLogger(__name__)

HA_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
]

FAN_MODES = ["auto", "night", "quiet", "low", "medium_low", "medium", "medium_high", "high", "powerful"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DaikinCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_config_entry_first_refresh()

    entities = [
        DaikinClimateEntity(coordinator, device)
        for device in coordinator.devices
    ]
    async_add_entities(entities)


class DaikinClimateEntity(CoordinatorEntity[DaikinCoordinator], ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = HA_HVAC_MODES
    _attr_fan_modes = FAN_MODES
    _attr_min_temp = 10.0
    _attr_max_temp = 32.0
    _attr_target_temperature_step = 0.5
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: DaikinCoordinator, device: DaikinDevice) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"daikin_{device.mac}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device.mac)},
            "name": device.name,
            "manufacturer": "Daikin",
            "model": "BRP069C4x",
            "sw_version": device.fw_ver,
        }

    @property
    def _state(self):
        return self.coordinator.data.get(self._device.mac)

    @property
    def available(self) -> bool:
        return self._state is not None

    @property
    def hvac_mode(self) -> HVACMode:
        s = self._state
        if not s or not s.power:
            return HVACMode.OFF
        mode_map = {
            "auto": HVACMode.AUTO,
            "cool": HVACMode.COOL,
            "heat": HVACMode.HEAT,
            "dry":  HVACMode.DRY,
            "fan_only": HVACMode.FAN_ONLY,
        }
        return mode_map.get(s.mode, HVACMode.COOL)

    @property
    def current_temperature(self) -> float | None:
        return self._state.indoor_temp if self._state else None

    @property
    def current_humidity(self) -> int | None:
        return self._state.indoor_humidity if self._state else None

    @property
    def target_temperature(self) -> float | None:
        return self._state.target_temp if self._state else None

    @property
    def fan_mode(self) -> str | None:
        s = self._state
        return DAIKIN_TO_HA_FAN.get(s.fan_rate if s else "A", "auto")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self._state
        if not s:
            return {}
        return {
            "outdoor_temp": s.outdoor_temp,
            "fan_dir_ud": s.fan_dir_ud,
            "fan_dir_lr": s.fan_dir_lr,
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.client.set_control(self._device, power=False)
        else:
            daikin_mode = {
                HVACMode.AUTO:     "auto",
                HVACMode.COOL:     "cool",
                HVACMode.HEAT:     "heat",
                HVACMode.DRY:      "dry",
                HVACMode.FAN_ONLY: "fan_only",
            }.get(hvac_mode, "cool")
            await self.coordinator.client.set_control(self._device, power=True, mode=daikin_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self.coordinator.client.set_control(self._device, target_temp=float(temp))
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.coordinator.client.set_control(self._device, fan_rate=fan_mode)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.coordinator.client.set_control(self._device, power=True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        await self.coordinator.client.set_control(self._device, power=False)
        await self.coordinator.async_request_refresh()
