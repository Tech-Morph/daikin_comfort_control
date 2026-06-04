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

# Keys that older versions of this integration may have stored credentials under.
# Maps old_key -> new_key. Order matters: first match wins.
_LEGACY_EMAIL_KEYS = ("username", "user", "email_address", "login")
_LEGACY_PASSWORD_KEYS = ("pass", "passwd", "pwd", "secret")


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry data from legacy key names to current schema.

    This runs automatically when the stored entry version is older than
    the current ConfigFlow VERSION. It also safely remaps any legacy
    credential key names regardless of version.
    """
    _LOGGER.debug(
        "Migrating Daikin Comfort Control entry from version %s", entry.version
    )
    new_data = dict(entry.data)
    changed = False

    # Remap legacy email keys
    if CONF_EMAIL not in new_data:
        for old_key in _LEGACY_EMAIL_KEYS:
            if old_key in new_data:
                _LOGGER.warning(
                    "Migrating config entry: renaming '%s' -> 'email'", old_key
                )
                new_data[CONF_EMAIL] = new_data.pop(old_key)
                changed = True
                break

    # Remap legacy password keys
    if CONF_PASSWORD not in new_data:
        for old_key in _LEGACY_PASSWORD_KEYS:
            if old_key in new_data:
                _LOGGER.warning(
                    "Migrating config entry: renaming '%s' -> 'password'", old_key
                )
                new_data[CONF_PASSWORD] = new_data.pop(old_key)
                changed = True
                break

    if changed:
        hass.config_entries.async_update_entry(entry, data=new_data, version=1)
        _LOGGER.info("Daikin Comfort Control config entry migrated successfully")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Daikin Comfort Control from a config entry."""

    email = entry.data.get(CONF_EMAIL)
    password = entry.data.get(CONF_PASSWORD)

    if not email or not password:
        _LOGGER.error(
            "Daikin Comfort Control config entry is missing 'email' or 'password'. "
            "Delete and re-add the integration to fix this. "
            "Entry data keys present: %s",
            list(entry.data.keys()),
        )
        return False

    session = async_get_clientsession(hass)
    api = DaikinComfortControlAPI(
        email=email,
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
        if not device_id:
            _LOGGER.warning("Device entry missing id field, skipping: %s", device)
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
