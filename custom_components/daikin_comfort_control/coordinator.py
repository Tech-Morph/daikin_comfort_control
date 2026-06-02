"""DataUpdateCoordinator for Daikin Comfort Control."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .daikin_api import DaikinCloudClient, DaikinDevice, DaikinState, DaikinAPIError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)


class DaikinCoordinator(DataUpdateCoordinator[DaikinState]):
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
        super().__init__(
            hass,
            _LOGGER,
            name=f"Daikin {device.name}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> DaikinState:
        """Fetch latest state from the cloud API."""
        try:
            return await self.client.get_state(self.device)
        except DaikinAuthError as err:
            raise UpdateFailed(f"Auth error: {err}") from err
        except DaikinAPIError as err:
            raise UpdateFailed(f"API error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err
