"""DataUpdateCoordinator for Daikin Comfort Control."""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import timedelta
from time import monotonic

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import HA_TO_DAIKIN_FAN, HA_TO_DAIKIN_MODE
from .daikin_api import DaikinCloudClient, DaikinDevice, DaikinState, DaikinAPIError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)

# Seconds after a write command during which scheduled polls are suppressed.
WRITE_SETTLE_SECONDS = 20

# Seconds after a write command before we do a single confirmatory poll.
WRITE_CONFIRM_DELAY = 15


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
        """Fetch latest state from the cloud API.

        Skips the poll if we are still within WRITE_SETTLE_SECONDS of a
        write command to prevent a race between an in-flight command and
        a scheduled poll returning stale state.
        """
        if (monotonic() - self._last_write_time) < WRITE_SETTLE_SECONDS:
            _LOGGER.debug(
                "Skipping poll for %s — within write-settle window",
                self.device.name,
            )
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
        raw_overrides: dict[str, str] | None = None,
    ) -> None:
        """Patch coordinator.data in-place with the values we just sent.

        fan_rate must be passed as the HA label (e.g. "low", "auto").
        This method converts it to the raw Daikin code (e.g. "3", "A")
        before storing in DaikinState.fan_rate so that DAIKIN_TO_HA_FAN
        lookups in climate.fan_mode always find the correct key.
        """
        if self.data is None:
            return

        # Convert HA fan label → raw Daikin code for DaikinState storage.
        # DaikinState.fan_rate mirrors what _parse_kv returns from the API
        # (raw codes), so we must store the same type here.
        raw_fan_code: str | None = None
        if fan_rate is not None:
            raw_fan_code = HA_TO_DAIKIN_FAN.get(fan_rate, "A")

        old_state = self.data.state
        new_state = replace(
            old_state,
            power=power if power is not None else old_state.power,
            mode=mode if mode is not None else old_state.mode,
            target_temp=target_temp if target_temp is not None else old_state.target_temp,
            # Store raw Daikin code, NOT the HA label
            fan_rate=raw_fan_code if raw_fan_code is not None else old_state.fan_rate,
        )

        new_raw = dict(self.data.raw_control)
        if raw_overrides:
            new_raw.update(raw_overrides)

        # Keep raw_control consistent with the patched state.
        # All values MUST be strings — raw_control mirrors _parse_kv output.
        if power is not None:
            new_raw["pow"] = "1" if power else "0"
        if mode is not None:
            new_raw["mode"] = str(HA_TO_DAIKIN_MODE.get(mode, 3))
        if target_temp is not None:
            new_raw["stemp"] = f"{target_temp:.1f}"
        if raw_fan_code is not None:
            new_raw["f_rate"] = raw_fan_code

        self.async_set_updated_data(DaikinData(state=new_state, raw_control=new_raw))

        self._last_write_time = monotonic()

        async_call_later(
            self.hass,
            WRITE_CONFIRM_DELAY,
            self._async_confirm_write,
        )

    async def _async_confirm_write(self, _now=None) -> None:
        """Confirmatory poll fired WRITE_CONFIRM_DELAY seconds after a write."""
        self._last_write_time = 0.0
        await self.async_refresh()
