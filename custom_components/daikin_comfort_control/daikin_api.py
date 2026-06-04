"""Async API client for Daikin Comfort Control (scr.daikincloud.net).

All endpoints and schemas confirmed via mitmproxy capture of the official
Daikin Comfort Control Android app (okhttp/4.9.2) on 2026-06-04.

=== AUTH ===
POST /common/login
  Headers: x-daikin-uid: <uid>, content-type: application/x-www-form-urlencoded
  Body:    grant_type=password&scope=smart_app&username=<u>&password=<p>
  Response (JSON):
    {"access_token": "<tok>", "refresh_token": "<tok>", "expires_in": "600"}

=== ALL SUBSEQUENT REQUESTS ===
  Headers:
    authentication: bearer <token>    <- non-standard header name, lowercase!
    x-daikin-uid: <uid>
    user-agent: okhttp/4.9.2

=== DEVICE LIST ===
GET /common/device_list
  Response (text/plain) — single flat KV string, ONE device per account:
    ret=OK,type=aircon,ver=3_1_0,port=30050,id=TechMorph,pw=,reg=us,
    pow=1,err=0,name=DaikinAP07464,...

=== CONTROL STATE ===
GET /aircon/get_control_info?port=30050&apw=&id=<username>&spw=
  Response: ret=OK,pow=1,mode=3,stemp=19.5,shum=0,...,f_rate=5,
            f_dir_ud=0,f_dir_lr=0,...

GET /aircon/get_sensor_info?port=30050&id=&spw=   <- id is BLANK
  Response: ret=OK,htemp=18.0,hhum=50,otemp=15.0,err=0,cmpfreq=18,mompow=2

=== SET CONTROL ===
GET /aircon/set_control_info?port=30050&pow=1&mode=3&stemp=20.5&dt3=20.5
                             &f_rate=A&shum=0&f_dir_ud=0&f_dir_lr=0&dh3=0
  NOTE: dt3 must mirror stemp for mode=3. dh3=0 required.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import BASE_URL
from .exceptions import DaikinApiError, DaikinAuthError

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
_USER_AGENT = "okhttp/4.9.2"

_EP_LOGIN        = "/common/login"
_EP_DEVICE_LIST  = "/common/device_list"
_EP_SENSOR_INFO  = "/aircon/get_sensor_info"
_EP_CONTROL_INFO = "/aircon/get_control_info"
_EP_SET_CONTROL  = "/aircon/set_control_info"


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
        self._uid = uid
        self._session = session
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: float = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ auth

    async def authenticate(self) -> None:
        """Login with username/password. Response is JSON."""
        payload = aiohttp.FormData(quote_fields=False)
        payload.add_field("grant_type", "password")
        payload.add_field("scope",      "smart_app")
        payload.add_field("username",   self._username)
        payload.add_field("password",   self._password)

        data = await self._request("POST", _EP_LOGIN, data=payload, authenticated=False)

        # Response is JSON but handle KV string defensively
        parsed = _parse_kv(data) if isinstance(data, str) else (data or {})

        self._access_token  = parsed.get("access_token") or parsed.get("accessToken")
        self._refresh_token = parsed.get("refresh_token") or parsed.get("refreshToken")
        try:
            expires_in = int(parsed.get("expires_in", 600))
        except (ValueError, TypeError):
            expires_in = 600
        # Re-auth 30s before expiry
        self._token_expires_at = time.monotonic() + expires_in - 30

        if not self._access_token:
            _LOGGER.error("Login response contained no token: %s", data)
            raise DaikinAuthError("No access token in login response")
        _LOGGER.debug("Daikin auth OK, token valid for %ds", expires_in)

    async def _ensure_token(self) -> None:
        """Re-authenticate proactively when token is expired or missing."""
        if not self._access_token or time.monotonic() >= self._token_expires_at:
            async with self._lock:
                if not self._access_token or time.monotonic() >= self._token_expires_at:
                    _LOGGER.debug("Token expired/missing — re-authenticating")
                    await self.authenticate()

    # --------------------------------------------------------------- devices

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return list of registered devices.

        Server returns a single flat KV string (confirmed from capture):
          ret=OK,type=aircon,...,port=30050,id=TechMorph,...,name=DaikinAP07464,...
        Parsed and returned as a single-element list.
        """
        raw = await self._request("GET", _EP_DEVICE_LIST)
        _LOGGER.debug("device_list raw: %s", raw)

        if isinstance(raw, list):
            return raw

        if isinstance(raw, dict):
            if "id" in raw or "deviceId" in raw:
                return [raw]
            return raw.get("devices", raw.get("deviceList", [raw]))

        if isinstance(raw, str):
            parsed = _parse_kv(raw)
            if parsed.get("ret") == "OK":
                # Use ssid as name fallback (confirmed: ssid=DaikinAP07464)
                if "name" not in parsed:
                    parsed["name"] = parsed.get("ssid", parsed.get("id", "Daikin"))
                return [parsed]
            _LOGGER.warning("device_list ret!=OK: %s", raw)
            return []

        _LOGGER.warning("device_list unexpected type %s: %s", type(raw).__name__, raw)
        return []

    async def get_device_state(self, device_id: str) -> dict[str, Any]:
        """Fetch combined control + sensor state.

        Confirmed endpoint sequence from mitmproxy:
          1. GET /aircon/get_control_info?port=30050&apw=&id=<username>&spw=
             -> ret=OK,pow=1,mode=3,stemp=19.5,shum=0,...,f_rate=5,f_dir_ud=0,...
          2. GET /aircon/get_sensor_info?port=30050&id=&spw=  (id is BLANK)
             -> ret=OK,htemp=18.0,hhum=50,otemp=15.0,cmpfreq=18,mompow=2

        Both plain-text KV. Merged into one dict (control takes precedence).
        """
        # 1. Control state — id=username required
        ctrl_raw = await self._request(
            "GET", _EP_CONTROL_INFO,
            params={"port": "30050", "apw": "", "id": self._username, "spw": ""},
        )
        _LOGGER.debug("get_control_info raw: %s", ctrl_raw)
        ctrl = _parse_kv(ctrl_raw) if isinstance(ctrl_raw, str) else (ctrl_raw or {})

        # 2. Sensor state — id is blank (confirmed from capture)
        sensor_raw = await self._request(
            "GET", _EP_SENSOR_INFO,
            params={"port": "30050", "id": "", "spw": ""},
        )
        _LOGGER.debug("get_sensor_info raw: %s", sensor_raw)
        sensor = _parse_kv(sensor_raw) if isinstance(sensor_raw, str) else (sensor_raw or {})

        # Merge: sensor fills in temps, control state takes precedence
        combined = {**sensor, **ctrl}

        if combined.get("ret") != "OK":
            raise DaikinApiError(
                f"Device state error for {device_id} — "
                f"ctrl={ctrl_raw!r:.120} sensor={sensor_raw!r:.120}"
            )

        return combined

    # Alias so coordinator continues working without changes
    async def get_device(self, device_id: str) -> dict[str, Any]:
        return await self.get_device_state(device_id)

    async def set_device_parameters(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Send control parameters via set_control_info (GET with query params).

        Confirmed from mitmproxy: uses GET, not PUT/POST.
        dt3 must mirror stemp. dh3=0 required when setting temperature.
        """
        base: dict[str, Any] = {"port": "30050"}
        base.update(params)

        if "stemp" in base:
            if "dt3" not in base:
                base["dt3"] = base["stemp"]
            if "dh3" not in base:
                base["dh3"] = "0"

        result_raw = await self._request("GET", _EP_SET_CONTROL, params=base)
        result = _parse_kv(result_raw) if isinstance(result_raw, str) else (result_raw or {})
        if result.get("ret") != "OK":
            raise DaikinApiError(f"set_control_info failed: {result_raw!r:.200}")
        _LOGGER.debug("set_control_info OK params=%s", params)

    # --------------------------------------------------------- http plumbing

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: aiohttp.FormData | None = None,
        params: dict | None = None,
        authenticated: bool = True,
        _retry: bool = True,
    ) -> Any:
        if authenticated:
            await self._ensure_token()

        url = BASE_URL + path
        headers: dict[str, str] = {
            "x-daikin-uid":    self._uid,
            "user-agent":      _USER_AGENT,
            "accept-encoding": "gzip",
        }
        if authenticated and self._access_token:
            headers["authentication"] = f"bearer {self._access_token}"

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(
                    method, url, data=data, params=params, headers=headers
                ) as resp:
                    if resp.status == 401 and authenticated and _retry:
                        _LOGGER.debug("401 — forcing re-auth")
                        async with self._lock:
                            self._access_token = None
                            self._token_expires_at = 0.0
                        return await self._request(
                            method, path,
                            data=data, params=params,
                            authenticated=True, _retry=False,
                        )
                    if resp.status == 401:
                        raise DaikinAuthError("Authentication failed (401)")
                    if resp.status == 429:
                        raise DaikinApiError("Rate limited (429)")
                    if not resp.ok:
                        text = await resp.text()
                        raise DaikinApiError(
                            f"{method} {path} -> HTTP {resp.status}: {text[:200]}"
                        )
                    ct = resp.content_type or ""
                    if "json" in ct:
                        return await resp.json()
                    return await resp.text()
        except asyncio.TimeoutError as err:
            raise DaikinApiError(f"Timeout: {method} {path}") from err
        except aiohttp.ClientError as err:
            raise DaikinApiError(f"Network error: {err}") from err


# ------------------------------------------------------------------ helpers

def _parse_kv(text: str) -> dict[str, str]:
    """Parse Daikin plain-text key=value,key=value responses.

    Confirmed response examples:
      'ret=OK,pow=1,mode=3,stemp=19.5,shum=0,f_rate=5,f_dir_ud=0,...'
      'ret=OK,htemp=18.0,hhum=50,otemp=15.0,err=0,cmpfreq=18,mompow=2'
      'ret=OK,type=aircon,...,port=30050,id=TechMorph,...'
    """
    result: dict[str, str] = {}
    for pair in text.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, _, v = pair.partition("=")
            result[k.strip()] = v.strip()
    return result
