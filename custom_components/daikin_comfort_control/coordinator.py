"""DataUpdateCoordinator for Daikin Comfort Control."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .daikin_api import DaikinComfortControlAPI
from .exceptions import DaikinApiError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)


class DaikinCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and cache Daikin device state."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DaikinComfortControlAPI,
        entry: ConfigEntry,
        device_id: str,
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch device state — called by coordinator on every poll cycle."""
        try:
            return await self.api.get_device(self.device_id)
        except DaikinAuthError as err:
            raise ConfigEntryAuthFailed(f"Auth error polling device: {err}") from err
        except DaikinApiError as err:
            raise UpdateFailed(f"Error polling Daikin device {self.device_id}: {err}") from err
