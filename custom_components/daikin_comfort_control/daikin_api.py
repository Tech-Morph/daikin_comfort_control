"""Async API client for Daikin Comfort Control (scr.daikincloud.net).

All requests confirmed via mitmproxy capture of the official
Daikin Comfort Control Android app (okhttp/4.9.2).

Auth flow:
  POST /common/login
  Headers: x-daikin-uid: <uid>, content-type: application/x-www-form-urlencoded; charset=utf-8
  Body:    grant_type=password&scope=smart_app&username=<u>&password=<p>

All subsequent requests:
  Headers: authentication: bearer <token>   (non-standard name, lowercase)
           x-daikin-uid: <uid>
           user-agent: okhttp/4.9.2

Control read:
  GET /aircon/get_control_info?port=30050&id=<username>&apw=&spw=

Control write:
  GET /aircon/set_control_info?port=30050&pow=1&mode=3&stemp=20.5&dt3=20.5
                               &f_rate=A&f_dir_ud=0&f_dir_lr=0&shum=0&dh3=0
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
    ENDPOINT_DEVICES,
    ENDPOINT_GET_CONTROL,
    ENDPOINT_SET_CONTROL,
)
from .exceptions import DaikinApiError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
# Must match the app or the server may reject requests
_USER_AGENT = "okhttp/4.9.2"


class DaikinComfortControlAPI:
    """Thin async client for the Daikin Comfort Control cloud API."""

    def __init__(
        self,
        username: str,
        password: str,
        uid: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._username = username
        self._password = password
        self._uid = uid          # x-daikin-uid — static app device fingerprint
        self._session = session
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ auth

    async def authenticate(self) -> None:
        """Login — form-encoded body, uid header, no bearer token yet."""
        payload = aiohttp.FormData(quote_fields=False)
        payload.add_field("grant_type", "password")
        payload.add_field("scope",      "smart_app")
        payload.add_field("username",   self._username)
        payload.add_field("password",   self._password)

        data = await self._request(
            "POST", ENDPOINT_AUTH, data=payload, authenticated=False
        )

        self._access_token = (
            data.get("accessToken") or data.get("access_token")
        )
        self._refresh_token = (
            data.get("refreshToken") or data.get("refresh_token")
        )
        if not self._access_token:
            raise DaikinAuthError("No access token in login response")
        _LOGGER.debug("Daikin auth successful")

    async def _refresh_access_token(self) -> None:
        if not self._refresh_token:
            raise DaikinAuthError("No refresh token available")
        payload = aiohttp.FormData(quote_fields=False)
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
        result = await self._request("GET", ENDPOINT_DEVICES)
        # Response may be a list directly or wrapped in a key
        if isinstance(result, list):
            return result
        return result.get("devices", result.get("deviceList", []))

    async def get_device(self, device_id: str) -> dict[str, Any]:
        """Return current control state for a device.

        Confirmed params: port=30050, id=<username>, apw='', spw=''
        """
        return await self._request(
            "GET",
            ENDPOINT_GET_CONTROL,
            params={
                "port": "30050",
                "id":   self._username,
                "apw":  "",
                "spw":  "",
            },
        )

    async def set_device_parameters(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Send control parameters.

        Confirmed: uses GET with query params, not PUT/POST.
        Always includes port=30050. When setting stemp, dt3 must
        mirror it and dh3=0 must be present (confirmed via mitmproxy).
        """
        base: dict[str, Any] = {"port": "30050"}
        base.update(params)
        # Mirror stemp -> dt3 if caller didn't already include it
        if "stemp" in base and "dt3" not in base:
            base["dt3"] = base["stemp"]
        if "stemp" in base and "dh3" not in base:
            base["dh3"] = "0"
        await self._request("GET", ENDPOINT_SET_CONTROL, params=base)

    # --------------------------------------------------------- http plumbing

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: aiohttp.FormData | None = None,
        params: dict | None = None,
        authenticated: bool = True,
        _retry_auth: bool = True,
    ) -> Any:
        url = BASE_URL + path

        # x-daikin-uid and user-agent are sent on EVERY request (incl. login)
        headers: dict[str, str] = {
            "x-daikin-uid": self._uid,
            "user-agent":   _USER_AGENT,
            "accept-encoding": "gzip",
        }

        # Bearer token added after login; login itself is unauthenticated
        if authenticated:
            if not self._access_token:
                await self.authenticate()
            headers["authentication"] = f"bearer {self._access_token}"

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(
                    method, url, data=data, params=params, headers=headers
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
                            data=data, params=params,
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
                    # Plain-text response (e.g. ret=OK,... from control endpoints)
                    return await resp.text()
        except asyncio.TimeoutError as err:
            raise DaikinApiError(f"Request timed out: {method} {path}") from err
        except aiohttp.ClientError as err:
            raise DaikinApiError(f"Network error: {err}") from err
