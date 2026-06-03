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


def _c_to_f(celsius: float) -> float:
    """Convert Celsius to Fahrenheit, rounded to nearest 1°F integer."""
    return round(celsius * 9 / 5 + 32)


def _f_to_c(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius, rounded to nearest 0.5°C step.

    The Daikin API accepts stemp in 0.5°C increments.  We round to the
    nearest step so that e.g. 68°F → 20.0°C (not 20.0°C raw 20.0).
    """
    raw = (fahrenheit - 32) * 5 / 9
    return round(raw * 2) / 2


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
    """Represents a single Daikin mini-split unit.

    Temperature unit: FAHRENHEIT (North American Skyport cloud / BRP069C4x)
    -----------------------------------------------------------------------
    The device is sold and operated in °F: range 64–90°F in 1° increments.
    We own the unit natively so HA performs zero auto-conversion.

    Internally the Daikin cloud API still accepts stemp in °C (e.g. 20.0).
    All °F ↔ °C conversion is done in this class:
      - Outbound to HA  : _c_to_f()  (current_temp, target_temp)
      - Inbound from HA : _f_to_c()  (async_set_temperature)
    """

    _attr_temperature_unit        = UnitOfTemperature.FAHRENHEIT
    _attr_target_temperature_step = 1.0    # 1°F increments
    _attr_min_temp                = 64.0   # confirmed NA Daikin minimum
    _attr_max_temp                = 90.0   # confirmed NA Daikin maximum
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
        """Indoor temperature in °F (our native unit)."""
        t = self._state.indoor_temp
        return _c_to_f(t) if t != 0.0 else None

    @property
    def target_temperature(self) -> float | None:
        """Target temperature in °F (our native unit)."""
        t = self._state.target_temp   # stored as °C in DaikinState
        return _c_to_f(t) if t is not None else None

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
        ot = self._state.outdoor_temp
        if ot != 0.0:
            attrs["outdoor_temperature_f"] = _c_to_f(ot)
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
            await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """HA passes °F (our native unit); convert to nearest 0.5°C for the API."""
        temp_f = kwargs.get(ATTR_TEMPERATURE)
        if temp_f is None:
            return
        temp_c = _f_to_c(float(temp_f))
        client = self.coordinator.client
        device = self.coordinator.device
        try:
            await client.set_control(device, target_temp=temp_c)
            # set_optimistic_data stores target_temp in °C — matches DaikinState
            self.coordinator.set_optimistic_data(target_temp=temp_c)
        except DaikinAPIError as err:
            _LOGGER.error("Failed to set temperature %s°F (%s°C): %s", temp_f, temp_c, err)
            await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        client = self.coordinator.client
        device = self.coordinator.device
        try:
            await client.set_control(device, fan_rate=fan_mode)
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
