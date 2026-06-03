"""DataUpdateCoordinator for Daikin Comfort Control."""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import timedelta
from time import monotonic

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import HA_TO_DAIKIN_FAN, HA_TO_DAIKIN_MODE, HA_TO_DAIKIN_SWING
from .daikin_api import DaikinCloudClient, DaikinDevice, DaikinState, DaikinAPIError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)

WRITE_SETTLE_SECONDS = 20
WRITE_CONFIRM_DELAY  = 15


@dataclass
class DaikinData:
    """Combined state + raw control_info for a single device poll cycle."""
    state: DaikinState
    raw_control: dict[str, str]


class DaikinCoordinator(DataUpdateCoordinator[DaikinData]):
    """Polls a single Daikin device and exposes its state."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: DaikinCloudClient,
        device: DaikinDevice,
        scan_interval: int,
    ) -> None:
        self.client = client
        self.device = device
        self._last_write_time: float = 0.0
        super().__init__(
            hass,
            _LOGGER,
            name=f"Daikin {device.name}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> DaikinData:
        if (monotonic() - self._last_write_time) < WRITE_SETTLE_SECONDS:
            _LOGGER.debug("Skipping poll for %s — within write-settle window", self.device.name)
            if self.data is not None:
                return self.data

        try:
            state, raw_control = await self.client.get_state_with_raw(self.device)
            return DaikinData(state=state, raw_control=raw_control)
        except DaikinAuthError as err:
            raise UpdateFailed(f"Auth error: {err}") from err
        except DaikinAPIError as err:
            raise UpdateFailed(f"API error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

    @callback
    def set_optimistic_data(
        self,
        *,
        power: bool | None = None,
        mode: str | None = None,
        target_temp: float | None = None,
        fan_rate: str | None = None,
        swing_mode: str | None = None,
        raw_overrides: dict[str, str] | None = None,
    ) -> None:
        """Patch coordinator.data in-place immediately after a write command.

        fan_rate  : HA label ("low", "auto", etc.) — converted to raw Daikin code
        swing_mode: HA label ("off", "vertical", etc.) — stored directly in DaikinState
        """
        if self.data is None:
            return

        # Convert HA fan label → raw Daikin code (must match _parse_kv format)
        raw_fan_code: str | None = None
        if fan_rate is not None:
            raw_fan_code = HA_TO_DAIKIN_FAN.get(fan_rate, "A")

        old_state = self.data.state
        new_state = replace(
            old_state,
            power       = power       if power       is not None else old_state.power,
            mode        = mode        if mode        is not None else old_state.mode,
            target_temp = target_temp if target_temp is not None else old_state.target_temp,
            fan_rate    = raw_fan_code if raw_fan_code is not None else old_state.fan_rate,
            swing_mode  = swing_mode  if swing_mode  is not None else old_state.swing_mode,
        )

        new_raw = dict(self.data.raw_control)
        if raw_overrides:
            new_raw.update(raw_overrides)

        if power is not None:
            new_raw["pow"] = "1" if power else "0"
        if mode is not None:
            new_raw["mode"] = str(HA_TO_DAIKIN_MODE.get(mode, 3))
        if target_temp is not None:
            new_raw["stemp"] = f"{target_temp:.1f}"
        if raw_fan_code is not None:
            new_raw["f_rate"] = raw_fan_code
        if swing_mode is not None:
            dfd3, fdir_ud, fdir_lr = HA_TO_DAIKIN_SWING.get(swing_mode, ("0", "0", "0"))
            new_raw["dfd3"]    = dfd3
            new_raw["f_dir_ud"] = fdir_ud
            new_raw["f_dir_lr"] = fdir_lr

        self.async_set_updated_data(DaikinData(state=new_state, raw_control=new_raw))
        self._last_write_time = monotonic()
        async_call_later(self.hass, WRITE_CONFIRM_DELAY, self._async_confirm_write)

    async def _async_confirm_write(self, _now=None) -> None:
        self._last_write_time = 0.0
        await self.async_refresh()
