"""Daikin Comfort Control integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
from .coordinator import DaikinCoordinator
from .daikin_api import DaikinComfortControlAPI
from .exceptions import DaikinApiError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.CLIMATE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Daikin Comfort Control from a config entry."""
    session = async_get_clientsession(hass)
    api = DaikinComfortControlAPI(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        session=session,
    )

    try:
        await api.authenticate()
        devices = await api.get_devices()
    except DaikinAuthError as err:
        _LOGGER.error("Authentication failed: %s", err)
        return False
    except DaikinApiError as err:
        _LOGGER.error("Failed to fetch devices: %s", err)
        return False

    coordinators = []
    for device in devices:
        device_id = device.get("id") or device.get("deviceId")
        if not device_id:
            _LOGGER.warning("Device entry missing id field: %s", device)
            continue
        coord = DaikinCoordinator(hass, api, entry, device_id)
        await coord.async_config_entry_first_refresh()
        coordinators.append(coord)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"api": api, "coordinators": coordinators}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
