"""Config flow for Daikin Comfort Control."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_UID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .daikin_api import DaikinCloudClient, DaikinAuthError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_UID): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=300)
        ),
    }
)


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate credentials by attempting login. Returns device title."""
    session = aiohttp.ClientSession()
    try:
        client = DaikinCloudClient(
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            uid=data[CONF_UID],
            session=session,
        )
        await client.login()
        devices = await client.get_devices()
        title = devices[0].name if devices else data[CONF_USERNAME]
    finally:
        await session.close()
    return {"title": title}


class DaikinComfortControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Daikin Comfort Control."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _validate_input(self.hass, user_input)
            except DaikinAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow validation")
                errors["base"] = "cannot_connect"
            else:
                # Prevent duplicate entries for the same UID
                await self.async_set_unique_id(user_input[CONF_UID])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
