"""Daikin Comfort Control integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_USERNAME, CONF_PASSWORD, CONF_UID, DOMAIN
from .coordinator import DaikinCoordinator
from .daikin_api import DaikinComfortControlAPI
from .exceptions import DaikinApiError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Daikin Comfort Control from a config entry."""
    username = entry.data.get(CONF_USERNAME, "")
    password = entry.data.get(CONF_PASSWORD, "")
    uid      = entry.data.get(CONF_UID, "")

    if not username or not password or not uid:
        _LOGGER.error(
            "Config entry missing required fields. Keys present: %s",
            list(entry.data.keys()),
        )
        return False

    session = async_get_clientsession(hass)
    api = DaikinComfortControlAPI(
        username=username,
        password=password,
        uid=uid,
        session=session,
    )

    try:
        await api.authenticate()
    except DaikinAuthError as err:
        _LOGGER.error("Authentication failed: %s", err)
        return False
    except DaikinApiError as err:
        _LOGGER.error("Cannot connect to Daikin cloud: %s", err)
        return False

    # Attempt device discovery but log whatever comes back for schema analysis.
    # If discovery returns nothing we fall back to a single synthesised device
    # built from the credentials we already know work (confirmed via mitmproxy:
    # get_control_info uses port=30050 and id=<username>).
    try:
        raw_devices = await api.get_devices()
        _LOGGER.debug("get_devices returned %d item(s): %s", len(raw_devices), raw_devices)
    except DaikinApiError as err:
        _LOGGER.warning("get_devices failed (%s) — falling back to synthesised device", err)
        raw_devices = []

    if raw_devices:
        devices = raw_devices
    else:
        # Fallback: synthesise one device from the username we authenticated with.
        # device_id is used as the 'id' param in get/set_control_info.
        _LOGGER.warning(
            "get_devices returned no devices — using synthesised device for '%s'. "
            "Enable debug logging and paste the get_devices log line to fix discovery.",
            username,
        )
        devices = [{"id": username, "name": f"Daikin ({username})"}]

    coordinators: list[DaikinCoordinator] = []
    for device in devices:
        device_id   = device.get("id") or device.get("deviceId") or username
        device_name = device.get("name") or device.get("deviceName") or device_id
        coord = DaikinCoordinator(hass, api, entry, device_id, device_name)
        try:
            await coord.async_config_entry_first_refresh()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("First refresh failed for %s: %s", device_id, err)
        coordinators.append(coord)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
