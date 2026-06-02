"""Config flow for Daikin Comfort Control."""
from __future__ import annotations
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_USERNAME, CONF_UID, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .daikin_api import DaikinCloudClient, DaikinAuthError, DaikinAPIError

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME, description={"suggested_value": "you@example.com"}): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Required(
        CONF_UID,
        description={"suggested_value": "dcd2e719644c4716afc1f729e98b609c"},
    ): str,
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
})


class DaikinComfortControlFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client  = DaikinCloudClient(
                username = user_input[CONF_USERNAME],
                password = user_input[CONF_PASSWORD],
                uid      = user_input[CONF_UID],
                session  = session,
            )
            try:
                await client.login()
                devices = await client.get_devices()
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    await self.async_set_unique_id(
                        f"{DOMAIN}_{user_input[CONF_USERNAME]}"
                    )
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"Daikin ({user_input[CONF_USERNAME]})",
                        data={
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                            CONF_UID:      user_input[CONF_UID],
                        },
                        options={
                            CONF_SCAN_INTERVAL: user_input.get(
                                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                            ),
                        },
                    )
            except DaikinAuthError:
                errors["base"] = "invalid_auth"
            except (DaikinAPIError, aiohttp.ClientError) as err:
                _LOGGER.exception("Error during config flow: %s", err)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "DaikinOptionsFlowHandler":
        return DaikinOptionsFlowHandler(config_entry)


class DaikinOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_SCAN_INTERVAL, default=current): int,
            }),
        )
