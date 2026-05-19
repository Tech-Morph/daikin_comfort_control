from __future__ import annotations
import logging
import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_UID,
    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL,
)
from .daikin_api import DaikinCloudClient, DaikinAuthError, DaikinAPIError

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Required(CONF_UID, description={"suggested_value": ""}): str,
})

OPTIONS_SCHEMA = vol.Schema({
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(min=10, max=300)),
})


class DaikinComfortControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = aiohttp.ClientSession()
            try:
                client = DaikinCloudClient(
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    uid=user_input[CONF_UID],
                    session=session,
                )
                await client.login()
                devices = await client.get_devices()
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"Daikin ({user_input[CONF_USERNAME]})",
                        data=user_input,
                    )
            except DaikinAuthError:
                errors["base"] = "invalid_auth"
            except DaikinAPIError:
                errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Daikin setup")
                errors["base"] = "unknown"
            finally:
                await session.close()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "uid_hint": "Found in mitmproxy capture as x-daikin-uid header (e.g. 51952434f3074927863a37557c01a0bc)"
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return DaikinOptionsFlow(config_entry)


class DaikinOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self._config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_SCAN_INTERVAL, default=current_interval): vol.All(int, vol.Range(min=10, max=300)),
            }),
        )
