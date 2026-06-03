"""Daikin Comfort Control integration."""
from __future__ import annotations

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_UID, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .coordinator import DaikinCoordinator
from .daikin_api import DaikinCloudClient, DaikinAuthError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["climate", "sensor", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Daikin Comfort Control from a config entry."""
    session = aiohttp.ClientSession()

    client = DaikinCloudClient(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        uid=entry.data[CONF_UID],
        session=session,
    )

    try:
        await client.login()
        devices = await client.get_devices()
    except DaikinAuthError as err:
        await session.close()
        raise ConfigEntryNotReady(f"Daikin auth failed: {err}") from err
    except Exception as err:
        await session.close()
        raise ConfigEntryNotReady(f"Daikin setup failed: {err}") from err

    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinators: list[DaikinCoordinator] = []
    for device in devices:
        coordinator = DaikinCoordinator(hass, client, device, scan_interval)
        await coordinator.async_config_entry_first_refresh()
        coordinators.append(coordinator)

    hass.data.setdefault(DOMAIN, {})
    # Store as a flat list — all platform modules iterate over it directly
    hass.data[DOMAIN][entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinators: list[DaikinCoordinator] = hass.data[DOMAIN].pop(entry.entry_id)
        # Close the shared aiohttp session via the first coordinator's client
        if coordinators:
            await coordinators[0].client._session.close()
    return unload_ok
