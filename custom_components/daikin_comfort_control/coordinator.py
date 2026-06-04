"""DataUpdateCoordinator for Daikin Comfort Control."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, DAIKIN_MODE_COOL
from .daikin_api import DaikinComfortControlAPI
from .exceptions import DaikinApiError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)

# How long to suppress cloud polls after a set_control command.
# Daikin cloud propagation lag is ~5-15s; 20s gives comfortable headroom.
COMMAND_COOLDOWN_SECONDS = 20


@dataclass
class DaikinDeviceData:
    """Parsed device state exposed to platform entities."""

    # Identity
    device_id:   str = ""
    device_name: str = ""
    port:        str = "30050"

    # Power / mode
    power:   bool  = False
    mode:    int   = DAIKIN_MODE_COOL

    # Temperatures (Celsius)
    target_temp:  float = 22.0
    indoor_temp:  float = 0.0
    outdoor_temp: float = 0.0

    # Humidity
    indoor_humidity: int = 0

    # Fan
    fan_rate:  str = "A"

    # Swing
    f_dir_ud: str = "0"
    f_dir_lr: str = "0"

    # Compressor diagnostics
    cmpfreq: int = 0
    mompow:  int = 0

    # Vacation / holiday mode
    vacation: bool = False

    # Raw response preserved for sensors
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_device(raw: dict[str, Any], device_id: str) -> DaikinDeviceData:
    """Map a raw API response dict to a DaikinDeviceData instance."""

    def _float(key: str, default: float = 0.0) -> float:
        try:
            v = raw.get(key, default)
            return float(v) if v not in ("", None, "--") else default
        except (ValueError, TypeError):
            return default

    def _int(key: str, default: int = 0) -> int:
        try:
            v = raw.get(key, default)
            return int(v) if v not in ("", None, "--") else default
        except (ValueError, TypeError):
            return default

    def _bool(key: str) -> bool:
        return str(raw.get(key, "0")).strip() in ("1", "true", "True")

    return DaikinDeviceData(
        device_id=device_id,
        device_name=raw.get("name", raw.get("deviceName", device_id)),
        port=str(raw.get("port", "30050")),
        power=_bool("pow"),
        mode=_int("mode", DAIKIN_MODE_COOL),
        target_temp=_float("stemp", 22.0),
        indoor_temp=_float("htemp"),
        outdoor_temp=_float("otemp"),
        indoor_humidity=_int("hhum"),
        fan_rate=str(raw.get("f_rate", "A")),
        f_dir_ud=str(raw.get("f_dir_ud", "0")),
        f_dir_lr=str(raw.get("f_dir_lr", "0")),
        cmpfreq=_int("cmpfreq"),
        mompow=_int("mompow"),
        vacation=_bool("en_hol"),
        raw=raw,
    )


class DaikinCoordinator(DataUpdateCoordinator[DaikinDeviceData]):
    """Fetch and cache Daikin device state."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DaikinComfortControlAPI,
        entry: ConfigEntry,
        device_id: str,
        device_name: str,
    ) -> None:
        scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.device_id = device_id
        self.device_name = device_name
        # Timestamp of last set_control command (monotonic). 0 = never sent.
        self._command_sent_at: float = 0.0

    async def _async_update_data(self) -> DaikinDeviceData:
        """Fetch device state, skipping the network call during cooldown."""
        elapsed = time.monotonic() - self._command_sent_at
        if self._command_sent_at and elapsed < COMMAND_COOLDOWN_SECONDS:
            _LOGGER.debug(
                "Skipping poll for %s — within command cooldown (%.1fs remaining)",
                self.device_id,
                COMMAND_COOLDOWN_SECONDS - elapsed,
            )
            # Return the current optimistic data unchanged
            return self.data if self.data is not None else DaikinDeviceData(device_id=self.device_id)

        try:
            raw = await self.api.get_device(self.device_id)
            return _parse_device(raw, self.device_id)
        except DaikinAuthError as err:
            raise ConfigEntryAuthFailed(f"Auth error polling device: {err}") from err
        except DaikinApiError as err:
            raise UpdateFailed(f"Error polling Daikin device {self.device_id}: {err}") from err

    # ------------------------------------------------------------------
    # Optimistic helpers — called by entities after a successful set_control.
    # Every call resets the cooldown timer.
    # ------------------------------------------------------------------

    def _current(self) -> DaikinDeviceData:
        return self.data if self.data is not None else DaikinDeviceData(device_id=self.device_id)

    def _apply(self, **kwargs: Any) -> None:
        import dataclasses
        self._command_sent_at = time.monotonic()
        updated = dataclasses.replace(self._current(), **kwargs)
        self.async_set_updated_data(updated)

    def set_optimistic_power(self, power: bool) -> None:
        self._apply(power=power)

    def set_optimistic_mode(self, mode: int) -> None:
        self._apply(mode=mode)

    def set_optimistic_target_temp(self, temp_c: float) -> None:
        self._apply(target_temp=temp_c)

    def set_optimistic_fan_rate(self, fan_rate: str) -> None:
        self._apply(fan_rate=fan_rate)

    def set_optimistic_swing(self, f_dir_ud: str, f_dir_lr: str) -> None:
        self._apply(f_dir_ud=f_dir_ud, f_dir_lr=f_dir_lr)

    def set_optimistic_vacation(self, vacation: bool) -> None:
        self._apply(vacation=vacation)
