"""Climate platform for Daikin Comfort Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    SWING_OFF,
    SWING_VERTICAL,
    SWING_HORIZONTAL,
    SWING_BOTH,
)
from homeassistant.components.climate.const import FAN_AUTO, FAN_HIGH, FAN_LOW, FAN_MEDIUM
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    DAIKIN_TO_HA_FAN,
    HA_TO_DAIKIN_FAN,
    DAIKIN_MODE_AUTO,
    DAIKIN_MODE_COOL,
    DAIKIN_MODE_HEAT,
    DAIKIN_MODE_DRY,
    DAIKIN_MODE_FAN,
    MIN_TEMP_F,
    MAX_TEMP_F,
    TEMP_STEP_F,
)
from .coordinator import DaikinCoordinator, DaikinDeviceData
from .exceptions import DaikinApiError

_LOGGER = logging.getLogger(__name__)

FAN_QUIET = "quiet"
FAN_MEDIUM_LOW = "medium_low"
FAN_MEDIUM_HIGH = "medium_high"

FAN_MODES = [FAN_AUTO, FAN_QUIET, FAN_LOW, FAN_MEDIUM_LOW, FAN_MEDIUM, FAN_MEDIUM_HIGH, FAN_HIGH]
SWING_MODES = [SWING_OFF, SWING_VERTICAL, SWING_HORIZONTAL, SWING_BOTH]

HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
]

DAIKIN_INT_TO_HVAC: dict[int, HVACMode] = {
    DAIKIN_MODE_AUTO: HVACMode.AUTO,
    DAIKIN_MODE_COOL: HVACMode.COOL,
    DAIKIN_MODE_HEAT: HVACMode.HEAT,
    DAIKIN_MODE_DRY: HVACMode.DRY,
    DAIKIN_MODE_FAN: HVACMode.FAN_ONLY,
}
HVAC_TO_DAIKIN_INT: dict[HVACMode, int] = {v: k for k, v in DAIKIN_INT_TO_HVAC.items()}

_SWING_TO_DIRS: dict[str, tuple[str, str]] = {
    SWING_OFF: ("0", "0"),
    SWING_VERTICAL: ("S", "0"),
    SWING_HORIZONTAL: ("0", "S"),
    SWING_BOTH: ("S", "S"),
}
_DIRS_TO_SWING: dict[tuple[str, str], str] = {v: k for k, v in _SWING_TO_DIRS.items()}


def _c_to_f(celsius: float) -> float:
    return round(celsius * 9 / 5 + 32)


def _f_to_c(fahrenheit: float) -> float:
    raw = (fahrenheit - 32) * 5 / 9
    return round(raw * 2) / 2


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators: list[DaikinCoordinator] = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DaikinClimateEntity(coordinator) for coordinator in coordinators
    )


class DaikinClimateEntity(CoordinatorEntity[DaikinCoordinator], ClimateEntity):
    """Climate entity for a single Daikin mini-split.

    Temperature reported/accepted in FAHRENHEIT (native), 1 F step.
    Internal API calls always use Celsius (0.5 C precision).

    set_control_info requires the FULL state on every call — partial
    params cause the unit to revert omitted fields to defaults.

    NOTE: In fan-only mode, the unit's stemp value is not a real target
    (there's nothing to heat/cool toward when only circulating air) and
    Daikin firmware frequently resets it to a default (commonly 72°F)
    on its own, independent of anything HA or any integration sent.
    target_temperature returns None while in fan-only so the frontend
    doesn't display this meaningless, firmware-reset value as if it
    were an active setpoint.
    """

    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_target_temperature_step = TEMP_STEP_F
    _attr_min_temp = MIN_TEMP_F
    _attr_max_temp = MAX_TEMP_F
    _attr_hvac_modes = HVAC_MODES
    _attr_fan_modes = FAN_MODES
    _attr_swing_modes = SWING_MODES
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.device_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            name=coordinator.device_name,
            manufacturer="Daikin",
            model="BRP069C4x",
        )

    @property
    def _d(self) -> DaikinDeviceData:
        return self.coordinator.data

    def _full_params(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build a complete set_control_info payload from current state.

        Daikin requires all fields on every call. We snapshot the current
        coordinator data and let the caller override specific fields.
        dt3 always mirrors stemp (required for mode=3/cool).
        """
        d = self._d
        stemp = str(d.target_temp)
        params: dict[str, Any] = {
            "pow": "1" if d.power else "0",
            "mode": str(d.mode),
            "stemp": stemp,
            "dt3": stemp,
            "f_rate": d.fan_rate,
            "shum": "0",
            "f_dir_ud": d.f_dir_ud,
            "f_dir_lr": d.f_dir_lr,
            "dh3": "0",
        }
        if overrides:
            params.update(overrides)
            # Keep dt3 in sync if stemp was overridden
            if "stemp" in overrides and "dt3" not in overrides:
                params["dt3"] = overrides["stemp"]
        return params

    # ------------------------------------------------------------------
    # State properties
    # ------------------------------------------------------------------

    @property
    def hvac_mode(self) -> HVACMode:
        if not self._d.power:
            return HVACMode.OFF
        return DAIKIN_INT_TO_HVAC.get(self._d.mode, HVACMode.COOL)

    @property
    def current_temperature(self) -> float | None:
        t = self._d.indoor_temp
        return _c_to_f(t) if t != 0.0 else None

    @property
    def target_temperature(self) -> float | None:
        """Return None in fan-only mode.

        Setpoint is meaningless when only circulating air, and Daikin
        firmware is known to silently reset stemp to a default (often
        72°F) on its own while in this mode — independent of any
        command sent by HA. Displaying that value as a real target
        was misleading and previously caused a false manual-override
        detection in the companion smart_temperature integration.
        """
        if self._d.mode == DAIKIN_MODE_FAN:
            return None
        return _c_to_f(self._d.target_temp)

    @property
    def current_humidity(self) -> int | None:
        h = self._d.indoor_humidity
        return h if h > 0 else None

    @property
    def fan_mode(self) -> str:
        return DAIKIN_TO_HA_FAN.get(self._d.fan_rate, FAN_AUTO)

    @property
    def swing_mode(self) -> str:
        key = (self._d.f_dir_ud, self._d.f_dir_lr)
        return _DIRS_TO_SWING.get(key, SWING_OFF)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        ot = self._d.outdoor_temp
        if ot != 0.0:
            attrs["outdoor_temperature_f"] = _c_to_f(ot)
        return attrs

    # ------------------------------------------------------------------
    # Service handlers — each sends full state + its override
    # ------------------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        try:
            if hvac_mode == HVACMode.OFF:
                params = self._full_params({"pow": "0"})
                await self.coordinator.api.set_device_parameters(
                    self.coordinator.device_id, params
                )
                self.coordinator.set_optimistic_power(False)
            else:
                daikin_mode = HVAC_TO_DAIKIN_INT.get(hvac_mode, DAIKIN_MODE_COOL)
                params = self._full_params({"pow": "1", "mode": str(daikin_mode)})
                await self.coordinator.api.set_device_parameters(
                    self.coordinator.device_id, params
                )
                self.coordinator.set_optimistic_power(True)
                self.coordinator.set_optimistic_mode(daikin_mode)
        except DaikinApiError as err:
            _LOGGER.error("Failed to set HVAC mode %s: %s", hvac_mode, err)
            await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp_f = kwargs.get(ATTR_TEMPERATURE)
        if temp_f is None:
            return

        temp_c = _f_to_c(float(temp_f))
        stemp = str(temp_c)
        try:
            params = self._full_params({"stemp": stemp, "dt3": stemp})
            await self.coordinator.api.set_device_parameters(
                self.coordinator.device_id, params
            )
            self.coordinator.set_optimistic_target_temp(temp_c)
        except DaikinApiError as err:
            _LOGGER.error("Failed to set temperature %.1fF (%.1fC): %s", temp_f, temp_c, err)
            await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        daikin_fan = HA_TO_DAIKIN_FAN.get(fan_mode, "A")
        try:
            params = self._full_params({"f_rate": daikin_fan})
            await self.coordinator.api.set_device_parameters(
                self.coordinator.device_id, params
            )
            self.coordinator.set_optimistic_fan_rate(daikin_fan)
        except DaikinApiError as err:
            _LOGGER.error("Failed to set fan mode %s: %s", fan_mode, err)
            await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        ud, lr = _SWING_TO_DIRS.get(swing_mode, ("0", "0"))
        try:
            params = self._full_params({"f_dir_ud": ud, "f_dir_lr": lr})
            await self.coordinator.api.set_device_parameters(
                self.coordinator.device_id, params
            )
            self.coordinator.set_optimistic_swing(ud, lr)
        except DaikinApiError as err:
            _LOGGER.error("Failed to set swing mode %s: %s", swing_mode, err)
            await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        last_mode = DAIKIN_INT_TO_HVAC.get(self._d.mode, HVACMode.COOL)
        await self.async_set_hvac_mode(last_mode)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
