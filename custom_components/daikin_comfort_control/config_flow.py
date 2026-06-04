"""Config flow for Daikin Comfort Control."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import CONF_USERNAME, CONF_PASSWORD, CONF_UID, DOMAIN
from .daikin_api import DaikinComfortControlAPI
from .exceptions import DaikinApiError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)

# Only ask the user for credentials — uid is auto-generated
STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class DaikinComfortControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow UI for Daikin Comfort Control."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            # Generate a stable random device UID for x-daikin-uid header.
            # Format matches what the Daikin app sends: 32 hex chars, no dashes.
            uid = uuid.uuid4().hex

            session = async_create_clientsession(self.hass)
            api = DaikinComfortControlAPI(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                uid=uid,
                session=session,
            )
            try:
                await api.authenticate()
            except DaikinAuthError:
                errors["base"] = "invalid_auth"
            except DaikinApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Daikin auth")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME],
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_UID:      uid,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )
