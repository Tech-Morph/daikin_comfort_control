from __future__ import annotations
import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_UID, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .daikin_api import DaikinCloudClient, DaikinDevice, DaikinState, DaikinAuthError, DaikinAPIError

_LOGGER = logging.getLogger(__name__)


class DaikinCoordinator(DataUpdateCoordinator[dict[str, DaikinState]]):
    """Polls all devices and caches state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        self._session = aiohttp.ClientSession()
        self.client = DaikinCloudClient(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            uid=entry.data[CONF_UID],
            session=self._session,
        )
        self.devices: list[DaikinDevice] = []

        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self) -> dict[str, DaikinState]:
        try:
            if not self.devices:
                self.devices = await self.client.get_devices()

            states: dict[str, DaikinState] = {}
            for device in self.devices:
                states[device.mac] = await self.client.get_state(device)
            return states

        except DaikinAuthError as err:
            # Force re-login on next poll
            self.client._access_token = None
            self.client._refresh_token = None
            raise UpdateFailed(f"Auth error: {err}") from err
        except DaikinAPIError as err:
            raise UpdateFailed(f"API error: {err}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error: {err}") from err

    async def async_shutdown(self) -> None:
        await self._session.close()
