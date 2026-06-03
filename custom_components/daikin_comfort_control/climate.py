"""Climate platform for Daikin Comfort Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import FAN_AUTO, FAN_HIGH, FAN_LOW, FAN_MEDIUM
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DAIKIN_TO_HA_FAN, HA_TO_DAIKIN_FAN
from .coordinator import DaikinCoordinator
from .daikin_api import DaikinAPIError

_LOGGER = logging.getLogger(__name__)

FAN_QUIET       = "quiet"
FAN_MEDIUM_LOW  = "medium_low"
FAN_MEDIUM_HIGH = "medium_high"

FAN_MODES = [FAN_AUTO, FAN_QUIET, FAN_LOW, FAN_MEDIUM_LOW, FAN_MEDIUM, FAN_MEDIUM_HIGH, FAN_HIGH]

HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
]

DAIKIN_TO_HVAC: dict[str, HVACMode] = {
    "auto":     HVACMode.AUTO,
    "cool":     HVACMode.COOL,
    "heat":     HVACMode.HEAT,
    "dry":      HVACMode.DRY,
    "fan_only": HVACMode.FAN_ONLY,
}
HVAC_TO_DAIKIN: dict[HVACMode, str] = {v: k for k, v in DAIKIN_TO_HVAC.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = [
        DaikinClimateEntity(coordinator)
        for coordinator in data["coordinators"].values()
    ]
    async_add_entities(entities)


class DaikinClimateEntity(CoordinatorEntity[DaikinCoordinator], ClimateEntity):
    """Represents a single Daikin mini-split unit."""

    _attr_temperature_unit        = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp                = 17.5
    _attr_max_temp                = 32.5
    _attr_hvac_modes              = HVAC_MODES
    _attr_fan_modes               = FAN_MODES
    _attr_supported_features      = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator)
        device = coordinator.device
        self._attr_unique_id = f"{DOMAIN}_{device.uid}_{device.port}"
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
    def hvac_mode(self) -> HVACMode:
        if not self._state.power:
            return HVACMode.OFF
        return DAIKIN_TO_HVAC.get(self._state.mode, HVACMode.COOL)

    @property
    def current_temperature(self) -> float | None:
        return self._state.indoor_temp if self._state.indoor_temp != 0.0 else None

    @property
    def target_temperature(self) -> float | None:
        return self._state.target_temp

    @property
    def current_humidity(self) -> int | None:
        h = self._state.indoor_humidity
        return h if h > 0 else None

    @property
    def fan_mode(self) -> str:
        return DAIKIN_TO_HA_FAN.get(self._state.fan_rate, FAN_AUTO)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        if self._state.outdoor_temp != 0.0:
            attrs["outdoor_temperature_c"] = self._state.outdoor_temp
        return attrs

    # ------------------------------------------------------------------
    # Service handlers — optimistic update first, no immediate refresh
    # ------------------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        client = self.coordinator.client
        device = self.coordinator.device
        try:
            if hvac_mode == HVACMode.OFF:
                await client.set_control(device, power=False)
                self.coordinator.set_optimistic_data(power=False)
            else:
                daikin_mode = HVAC_TO_DAIKIN.get(hvac_mode, "cool")
                await client.set_control(device, power=True, mode=daikin_mode)
                self.coordinator.set_optimistic_data(power=True, mode=daikin_mode)
        except DaikinAPIError as err:
            _LOGGER.error("Failed to set HVAC mode %s: %s", hvac_mode, err)
            # On failure do a real refresh so we show actual device state
            await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        client = self.coordinator.client
        device = self.coordinator.device
        try:
            await client.set_control(device, target_temp=float(temp))
            self.coordinator.set_optimistic_data(target_temp=float(temp))
        except DaikinAPIError as err:
            _LOGGER.error("Failed to set temperature %s: %s", temp, err)
            await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        client = self.coordinator.client
        device = self.coordinator.device
        try:
            await client.set_control(device, fan_rate=fan_mode)
            # fan_rate in DaikinState uses HA names; set_optimistic_data
            # converts via HA_TO_DAIKIN_FAN for raw_control consistency
            self.coordinator.set_optimistic_data(
                fan_rate=fan_mode,
                raw_overrides={"f_rate": HA_TO_DAIKIN_FAN.get(fan_mode, "A")},
            )
        except DaikinAPIError as err:
            _LOGGER.error("Failed to set fan mode %s: %s", fan_mode, err)
            await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(
            DAIKIN_TO_HVAC.get(self._state.mode, HVACMode.COOL)
            if self._state.mode else HVACMode.COOL
        )

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
