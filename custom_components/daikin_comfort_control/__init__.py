"""Daikin Comfort Control integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_USERNAME, CONF_PASSWORD, DOMAIN
from .coordinator import DaikinCoordinator
from .daikin_api import DaikinComfortControlAPI
from .exceptions import DaikinApiError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]

# Legacy key names that older versions may have stored under.
_LEGACY_USERNAME_KEYS = ("email", "email_address", "user", "login")
_LEGACY_PASSWORD_KEYS = ("pass", "passwd", "pwd", "secret")


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry data from legacy key names to current schema."""
    _LOGGER.debug(
        "Checking Daikin Comfort Control entry for migration (version %s)", entry.version
    )
    new_data = dict(entry.data)
    changed = False

    if CONF_USERNAME not in new_data:
        for old_key in _LEGACY_USERNAME_KEYS:
            if old_key in new_data:
                _LOGGER.warning("Migrating config entry: renaming key '%s' -> 'username'", old_key)
                new_data[CONF_USERNAME] = new_data.pop(old_key)
                changed = True
                break

    if CONF_PASSWORD not in new_data:
        for old_key in _LEGACY_PASSWORD_KEYS:
            if old_key in new_data:
                _LOGGER.warning("Migrating config entry: renaming key '%s' -> 'password'", old_key)
                new_data[CONF_PASSWORD] = new_data.pop(old_key)
                changed = True
                break

    if changed:
        hass.config_entries.async_update_entry(entry, data=new_data, version=1)
        _LOGGER.info("Daikin Comfort Control config entry migrated successfully")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Daikin Comfort Control from a config entry."""
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)

    if not username or not password:
        _LOGGER.error(
            "Daikin Comfort Control config entry is missing 'username' or 'password'. "
            "Delete and re-add the integration to fix this. "
            "Entry data keys present: %s",
            list(entry.data.keys()),
        )
        return False

    session = async_get_clientsession(hass)
    api = DaikinComfortControlAPI(
        username=username,
        password=password,
        session=session,
    )

    try:
        await api.authenticate()
        devices = await api.get_devices()
    except DaikinAuthError as err:
        _LOGGER.error("Authentication failed: %s", err)
        return False
    except DaikinApiError as err:
        _LOGGER.error("Failed to fetch devices on setup: %s", err)
        return False

    coordinators: list[DaikinCoordinator] = []
    for device in devices:
        device_id = device.get("id") or device.get("deviceId")
        device_name = device.get("name") or device.get("deviceName") or device_id
        if not device_id:
            _LOGGER.warning("Device entry missing id field, skipping: %s", device)
            continue
        coord = DaikinCoordinator(hass, api, entry, device_id, device_name)
        await coord.async_config_entry_first_refresh()
        coordinators.append(coord)

    hass.data.setdefault(DOMAIN, {})
    # Store as a plain flat list — all platform files iterate this directly.
    hass.data[DOMAIN][entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
