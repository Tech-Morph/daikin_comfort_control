"""Async API client for Daikin Comfort Control (scr.daikincloud.net).

Auth confirmed via mitmproxy 2026-06-02:
  POST /common/login
  Content-Type: application/x-www-form-urlencoded
  Body: grant_type=password&scope=smart_app&username=<u>&password=<p>

  Subsequent requests use a non-standard header:
  authentication: bearer <token>          (NOT Authorization)
  x-daikin-uid: <device-uid>             (added per-request in set_device_parameters)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    ENDPOINT_AUTH,
    ENDPOINT_AUTH_REFRESH,
    ENDPOINT_DEVICE,
    ENDPOINT_DEVICES,
    ENDPOINT_SET_CONTROL,
)
from .exceptions import DaikinApiError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15


class DaikinComfortControlAPI:
    """Thin async client for the Daikin Comfort Control cloud API."""

    def __init__(self, username: str, password: str, session: aiohttp.ClientSession) -> None:
        self._username = username
        self._password = password
        self._session = session
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ auth

    async def authenticate(self) -> None:
        """Login with username/password using form-encoded body (confirmed via mitmproxy)."""
        # Must be x-www-form-urlencoded with grant_type + scope — NOT JSON
        payload = aiohttp.FormData()
        payload.add_field("grant_type", "password")
        payload.add_field("scope", "smart_app")
        payload.add_field("username", self._username)
        payload.add_field("password", self._password)

        data = await self._request("POST", ENDPOINT_AUTH, data=payload, authenticated=False)

        self._access_token = (
            data.get("accessToken")
            or data.get("access_token")
        )
        self._refresh_token = (
            data.get("refreshToken")
            or data.get("refresh_token")
        )
        if not self._access_token:
            raise DaikinAuthError("No access token in login response")
        _LOGGER.debug("Daikin auth successful")

    async def _refresh_access_token(self) -> None:
        """Use the refresh token to obtain a new access token."""
        if not self._refresh_token:
            raise DaikinAuthError("No refresh token available — re-login required")
        payload = aiohttp.FormData()
        payload.add_field("refreshToken", self._refresh_token)
        try:
            data = await self._request(
                "POST", ENDPOINT_AUTH_REFRESH, data=payload, authenticated=False
            )
            self._access_token = (
                data.get("accessToken") or data.get("access_token")
            )
            if not self._access_token:
                raise DaikinAuthError("Token refresh returned no access token")
            _LOGGER.debug("Daikin token refreshed")
        except DaikinApiError as err:
            raise DaikinAuthError(f"Token refresh failed: {err}") from err

    # --------------------------------------------------------------- devices

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return list of all registered devices."""
        return await self._request("GET", ENDPOINT_DEVICES)

    async def get_device(self, device_id: str) -> dict[str, Any]:
        """Return current control state for a single device."""
        return await self._request(
            "GET", ENDPOINT_DEVICE, params={"port": "30050", "id": self._username}
        )

    async def set_device_parameters(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Send control parameters to a device via GET set_control_info."""
        # Confirmed via mitmproxy: control writes are GET requests with query params
        base_params = {"port": "30050"}
        base_params.update(params)
        await self._request("GET", ENDPOINT_SET_CONTROL, params=base_params)

    # --------------------------------------------------------- http plumbing

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: aiohttp.FormData | None = None,
        json: dict | None = None,
        params: dict | None = None,
        authenticated: bool = True,
        _retry_auth: bool = True,
    ) -> Any:
        url = BASE_URL + path

        # Non-standard auth header confirmed by mitmproxy: 'authentication' not 'Authorization'
        headers: dict[str, str] = {}
        if authenticated:
            if not self._access_token:
                await self.authenticate()
            headers["authentication"] = f"bearer {self._access_token}"

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(
                    method, url, data=data, json=json, params=params, headers=headers
                ) as resp:
                    if resp.status == 401 and authenticated and _retry_auth:
                        _LOGGER.debug("Got 401 — attempting token refresh")
                        async with self._lock:
                            try:
                                await self._refresh_access_token()
                            except DaikinAuthError:
                                await self.authenticate()
                        return await self._request(
                            method, path,
                            data=data, json=json, params=params,
                            authenticated=True, _retry_auth=False,
                        )
                    if resp.status == 401:
                        raise DaikinAuthError("Authentication failed (401)")
                    if resp.status == 429:
                        raise DaikinApiError("Rate limited by Daikin cloud (429)")
                    if not resp.ok:
                        text = await resp.text()
                        raise DaikinApiError(
                            f"API error {resp.status} for {method} {path}: {text[:200]}"
                        )
                    if resp.content_type and "json" in resp.content_type:
                        return await resp.json()
                    return {}
        except asyncio.TimeoutError as err:
            raise DaikinApiError(f"Request timed out: {method} {path}") from err
        except aiohttp.ClientError as err:
            raise DaikinApiError(f"Network error: {err}") from err
