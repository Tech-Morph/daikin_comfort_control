"""DataUpdateCoordinator for Daikin Comfort Control."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .daikin_api import DaikinCloudClient, DaikinDevice, DaikinState, DaikinAPIError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)


@dataclass
class DaikinData:
    """Combined state + raw control_info for a single device poll cycle."""
    state: DaikinState
    # Raw key=value dict from get_control_info, used by sensor platform
    # for values not promoted to DaikinState (e.g. f_dir_ud, f_dir_lr)
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
        super().__init__(
            hass,
            _LOGGER,
            name=f"Daikin {device.name}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> DaikinData:
        """Fetch latest state from the cloud API."""
        try:
            state, raw_control = await self.client.get_state_with_raw(self.device)
            return DaikinData(state=state, raw_control=raw_control)
        except DaikinAuthError as err:
            raise UpdateFailed(f"Auth error: {err}") from err
        except DaikinAPIError as err:
            raise UpdateFailed(f"API error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err
