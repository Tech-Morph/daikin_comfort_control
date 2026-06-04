"""Daikin Comfort Control climate entity — HA 2026.x compatible."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DAIKIN_FAN_AUTO,
    DAIKIN_FAN_HIGH,
    DAIKIN_FAN_LOW,
    DAIKIN_FAN_MEDIUM,
    DAIKIN_FAN_POWERFUL,
    DAIKIN_FAN_QUIET,
    DAIKIN_MODE_AUTO,
    DAIKIN_MODE_COOL,
    DAIKIN_MODE_DRY,
    DAIKIN_MODE_FAN,
    DAIKIN_MODE_HEAT,
    DAIKIN_MODE_OFF,
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
    TEMP_STEP,
)
from .coordinator import DaikinCoordinator
from .exceptions import DaikinApiError

_LOGGER = logging.getLogger(__name__)

# Map Daikin integer mode <-> HA HVACMode
_DAIKIN_TO_HA_MODE: dict[int, HVACMode] = {
    DAIKIN_MODE_OFF: HVACMode.OFF,
    DAIKIN_MODE_AUTO: HVACMode.AUTO,
    DAIKIN_MODE_DRY: HVACMode.DRY,
    DAIKIN_MODE_COOL: HVACMode.COOL,
    DAIKIN_MODE_HEAT: HVACMode.HEAT,
    DAIKIN_MODE_FAN: HVACMode.FAN_ONLY,
}
_HA_TO_DAIKIN_MODE: dict[HVACMode, int] = {v: k for k, v in _DAIKIN_TO_HA_MODE.items()}

# Map Daikin fan string <-> HA fan mode string
_DAIKIN_TO_HA_FAN: dict[str, str] = {
    DAIKIN_FAN_AUTO: FAN_AUTO,
    DAIKIN_FAN_QUIET: "quiet",
    DAIKIN_FAN_LOW: FAN_LOW,
    DAIKIN_FAN_MEDIUM: FAN_MEDIUM,
    DAIKIN_FAN_HIGH: FAN_HIGH,
    DAIKIN_FAN_POWERFUL: "powerful",
}
_HA_TO_DAIKIN_FAN: dict[str, str] = {v: k for k, v in _DAIKIN_TO_HA_FAN.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities for all discovered Daikin devices."""
    coordinators: list[DaikinCoordinator] = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    async_add_entities(
        DaikinClimateEntity(coordinator) for coordinator in coordinators
    )


class DaikinClimateEntity(CoordinatorEntity[DaikinCoordinator], ClimateEntity):
    """Climate entity for a single Daikin mini-split."""

    # ----------------------------------------------------------------
    # HA 2026.x FIX:
    # 1. Declare ALL features explicitly — including TURN_ON and TURN_OFF.
    #    The deprecation grace period has ended; HA no longer auto-sets these.
    # 2. _enable_turn_on_off_backwards_compatibility = False is REQUIRED
    #    to prevent HA's legacy compat check from interfering.
    # ----------------------------------------------------------------
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False  # REQUIRED for 2026.x

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    _attr_fan_modes = list(_DAIKIN_TO_HA_FAN.values())
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator)
        device_data = coordinator.data or {}
        self._device_id = coordinator.device_id
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_data.get("name", f"Daikin {self._device_id[:8]}"),
            manufacturer="Daikin",
            model=device_data.get("model", "Mini-split"),
            sw_version=device_data.get("firmwareVersion"),
        )

    # --------------------------------------------------------- state props

    @property
    def hvac_mode(self) -> HVACMode:
        data = self.coordinator.data or {}
        raw_mode = data.get("mode", DAIKIN_MODE_OFF)
        return _DAIKIN_TO_HA_MODE.get(raw_mode, HVACMode.OFF)

    @property
    def current_temperature(self) -> float | None:
        data = self.coordinator.data or {}
        return data.get("tempIndoor") or data.get("currentTemperature")

    @property
    def target_temperature(self) -> float | None:
        data = self.coordinator.data or {}
        return data.get("tempSet") or data.get("targetTemperature")

    @property
    def fan_mode(self) -> str | None:
        data = self.coordinator.data or {}
        raw_fan = data.get("fanSpeed") or data.get("fan", DAIKIN_FAN_AUTO)
        return _DAIKIN_TO_HA_FAN.get(str(raw_fan), FAN_AUTO)

    # --------------------------------------------------------- commands

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        daikin_mode = _HA_TO_DAIKIN_MODE.get(hvac_mode)
        if daikin_mode is None:
            _LOGGER.warning("Unsupported HVAC mode: %s", hvac_mode)
            return
        await self._send({"mode": daikin_mode})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature.

        HA 2026.x passes temperature via ATTR_TEMPERATURE in kwargs.
        Always use kwargs.get(ATTR_TEMPERATURE) — never positional args.
        """
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            _LOGGER.warning("async_set_temperature called with no temperature value")
            return
        await self._send({"tempSet": float(temperature)})

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        daikin_fan = _HA_TO_DAIKIN_FAN.get(fan_mode)
        if daikin_fan is None:
            _LOGGER.warning("Unsupported fan mode: %s", fan_mode)
            return
        await self._send({"fanSpeed": daikin_fan})

    async def async_turn_on(self) -> None:
        """Turn on — restore last non-OFF mode or default to COOL."""
        data = self.coordinator.data or {}
        last_mode = data.get("lastMode", DAIKIN_MODE_COOL)
        if last_mode == DAIKIN_MODE_OFF:
            last_mode = DAIKIN_MODE_COOL
        await self._send({"mode": last_mode})

    async def async_turn_off(self) -> None:
        """Turn off."""
        await self._send({"mode": DAIKIN_MODE_OFF})

    # --------------------------------------------------------- internals

    async def _send(self, params: dict[str, Any]) -> None:
        """Send params to device, then request a coordinator refresh."""
        try:
            await self.coordinator.api.set_device_parameters(self._device_id, params)
        except DaikinApiError as err:
            _LOGGER.error("Failed to send command to %s: %s", self._device_id, err)
            return
        # Force an immediate poll so the UI reflects the new state
        await self.coordinator.async_request_refresh()
