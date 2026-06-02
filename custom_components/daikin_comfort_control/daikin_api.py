"""
Daikin Comfort Control cloud API client.

Confirmed via mitmproxy traffic capture (2026-06-02):
  Base URL  : https://scr.daikincloud.net
  Auth      : POST /common/login  (application/x-www-form-urlencoded)
              Body: grant_type=password&scope=smart_app&username=<u>&password=<p>
              Response: JSON with access_token, refresh_token, expires_in (str "600")
  Auth hdrs : authentication: bearer <token>   <- non-standard header name
              x-daikin-uid: <static uid>
  User-Agent: okhttp/4.9.2
  Device list: GET /common/device_list
  Poll      : GET /aircon/get_control_info?port=30050&id=<username>&apw=&spw=
  Sensor    : GET /aircon/get_sensor_info?port=30050&id=<username>&apw=&spw=
  Control   : GET /aircon/set_control_info?port=30050&pow=&mode=&stemp=&...
  Success   : ret=OK,adv=
  Token TTL : 600 s -> refresh 30 s before expiry via /common/token_refresh
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    HA_TO_DAIKIN_MODE,
    DAIKIN_TO_HA_MODE,
    HA_TO_DAIKIN_FAN,
    DAIKIN_TO_HA_FAN,
    MODE_STEMP_SENTINEL,
    MODE_TEMP_PARAMS,
)

_LOGGER = logging.getLogger(__name__)
BASE_URL = "https://scr.daikincloud.net"
_UA = "okhttp/4.9.2"


@dataclass
class DaikinDevice:
    port: str
    name: str
    mac: str
    uid: str
    fw_ver: str
    region: str = ""


@dataclass
class DaikinState:
    power: bool
    mode: str
    target_temp: float | None
    indoor_temp: float
    indoor_humidity: int
    outdoor_temp: float
    fan_rate: str
    fan_dir: int


class DaikinAuthError(Exception):
    pass


class DaikinAPIError(Exception):
    pass


def _parse_kv(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in text.strip().split(","):
        if "=" in pair:
            k, _, v = pair.partition("=")
            result[k.strip()] = v.strip()
    return result


class DaikinCloudClient:
    """Async client for the Daikin Comfort Control cloud API."""

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
        self._token_expiry: float = 0.0

    def _headers(self, *, auth: bool = True) -> dict[str, str]:
        h: dict[str, str] = {
            "x-daikin-uid": self._uid,
            "user-agent": _UA,
            "accept-encoding": "gzip",
        }
        if auth and self._access_token:
            h["authentication"] = f"bearer {self._access_token}"
        return h

    async def login(self) -> None:
        url = f"{BASE_URL}/common/login"
        payload = {
            "grant_type": "password",
            "scope": "smart_app",
            "username": self._username,
            "password": self._password,
        }
        try:
            async with self._session.post(
                url, data=payload, headers=self._headers(auth=False), ssl=True
            ) as resp:
                if resp.status == 401:
                    raise DaikinAuthError("Invalid credentials (401)")
                if resp.status != 200:
                    body = await resp.text()
                    raise DaikinAuthError(f"Login HTTP {resp.status}: {body}")
                data: dict[str, Any] = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise DaikinAuthError(f"Network error during login: {err}") from err

        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        expires_in = int(data.get("expires_in", 600))
        self._token_expiry = time.monotonic() + expires_in - 30
        _LOGGER.debug("Daikin login OK, token expires in %ss", expires_in)

    async def _refresh_access_token(self) -> None:
        url = f"{BASE_URL}/common/token_refresh"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }
        try:
            async with self._session.post(
                url,
                data=payload,
                headers={
                    "user-agent": _UA,
                    "x-daikin-uid": self._uid,
                    "content-type": "application/x-www-form-urlencoded",
                },
                ssl=True,
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Token refresh failed (%s), falling back to re-login", resp.status)
                    await self.login()
                    return
                data: dict[str, Any] = await resp.json(content_type=None)
        except aiohttp.ClientError:
            _LOGGER.warning("Token refresh network error, falling back to re-login")
            await self.login()
            return

        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        expires_in = int(data.get("expires_in", 600))
        self._token_expiry = time.monotonic() + expires_in - 30
        _LOGGER.debug("Daikin token refreshed")

    async def ensure_token(self) -> None:
        if time.monotonic() >= self._token_expiry:
            if self._refresh_token:
                await self._refresh_access_token()
            else:
                await self.login()

    async def _get(self, path: str) -> str:
        url = f"{BASE_URL}{path}"
        async with self._session.get(url, headers=self._headers(), ssl=True) as resp:
            text = await resp.text()
            if resp.status == 401:
                _LOGGER.debug("401 on %s, re-authenticating", path)
                self._access_token = None
                await self.login()
                async with self._session.get(url, headers=self._headers(), ssl=True) as retry:
                    text = await retry.text()
                    if retry.status != 200:
                        raise DaikinAuthError(f"Still unauthorized after re-login: {retry.status}")
                    return text
            if resp.status != 200:
                raise DaikinAPIError(f"HTTP {resp.status} on {path}: {text[:200]}")
            return text

    async def get_devices(self) -> list[DaikinDevice]:
        await self.ensure_token()
        text = await self._get("/common/device_list")
        kv = _parse_kv(text)
        if kv.get("ret") != "OK":
            raise DaikinAPIError(f"device_list failed: {text[:200]}")

        devices: list[DaikinDevice] = []
        raw_device = kv.get("device", "")
        if raw_device:
            fields = raw_device.split(":")
            port = fields[0] if len(fields) > 0 else "30050"
            fw_ver = fields[4] if len(fields) > 4 else ""
            name = fields[8] if len(fields) > 8 else "DaikinAC"
            region = fields[11] if len(fields) > 11 else ""
            basic = await self._get_basic_info(port)
            mac = basic.get("mac", port)
            devices.append(
                DaikinDevice(
                    port=port,
                    name=name,
                    mac=mac,
                    uid=self._uid,
                    fw_ver=fw_ver,
                    region=region,
                )
            )

        if not devices:
            raise DaikinAPIError(f"No devices found in device_list: {text[:500]}")
        return devices

    async def _get_basic_info(self, port: str) -> dict[str, str]:
        text = await self._get(
            f"/common/basic_info?port={port}&lpw=&port={port}&apw=&id=&spw="
        )
        return _parse_kv(text)

    async def get_state(self, device: DaikinDevice) -> DaikinState:
        await self.ensure_token()
        ctrl_task = asyncio.create_task(self._get_control_info(device.port))
        sensor_task = asyncio.create_task(self._get_sensor_info(device.port))
        ctrl, sensor = await asyncio.gather(ctrl_task, sensor_task)

        mode_num = int(ctrl.get("mode", 3))
        mode_str = DAIKIN_TO_HA_MODE.get(mode_num, "cool")

        raw_stemp = ctrl.get("stemp", "22.0")
        try:
            target_temp: float | None = None if raw_stemp in ("M", "--", "") else float(raw_stemp)
        except ValueError:
            target_temp = None

        fan_rate = DAIKIN_TO_HA_FAN.get(ctrl.get("f_rate", "A"), "auto")

        try:
            indoor_humidity = int(float(ctrl.get("hhum") or sensor.get("hhum", 0) or 0))
        except (ValueError, TypeError):
            indoor_humidity = 0

        try:
            indoor_temp = float(sensor.get("htemp", 0) or 0)
        except (ValueError, TypeError):
            indoor_temp = 0.0

        try:
            outdoor_temp = float(sensor.get("otemp", 0) or 0)
        except (ValueError, TypeError):
            outdoor_temp = 0.0

        return DaikinState(
            power=ctrl.get("pow") == "1",
            mode=mode_str,
            target_temp=target_temp,
            indoor_temp=indoor_temp,
            indoor_humidity=indoor_humidity,
            outdoor_temp=outdoor_temp,
            fan_rate=fan_rate,
            fan_dir=int(ctrl.get("f_dir", 0) or 0),
        )

    async def _get_control_info(self, port: str) -> dict[str, str]:
        text = await self._get(
            f"/aircon/get_control_info?port={port}&id={self._username}&apw=&spw="
        )
        kv = _parse_kv(text)
        if kv.get("ret") != "OK":
            raise DaikinAPIError(f"get_control_info ret={kv.get('ret')}: {text[:200]}")
        return kv

    async def _get_sensor_info(self, port: str) -> dict[str, str]:
        text = await self._get(
            f"/aircon/get_sensor_info?port={port}&id={self._username}&apw=&spw="
        )
        kv = _parse_kv(text)
        if kv.get("ret") != "OK":
            raise DaikinAPIError(f"get_sensor_info ret={kv.get('ret')}: {text[:200]}")
        return kv

    async def set_control(
        self,
        device: DaikinDevice,
        *,
        power: bool | None = None,
        mode: str | None = None,
        target_temp: float | None = None,
        fan_rate: str | None = None,
        fan_dir: int | None = None,
    ) -> None:
        await self.ensure_token()
        current = await self._get_control_info(device.port)

        pow_val = ("1" if power else "0") if power is not None else current.get("pow", "0")

        current_mode_num = int(current.get("mode", 3))
        if mode is not None:
            mode_num = HA_TO_DAIKIN_MODE.get(mode, 3)
            mode_str = mode
        else:
            mode_num = current_mode_num
            mode_str = DAIKIN_TO_HA_MODE.get(mode_num, "cool")

        frate_val = (
            HA_TO_DAIKIN_FAN.get(fan_rate.lower(), current.get("f_rate", "A"))
            if fan_rate is not None
            else current.get("f_rate", "A")
        )
        shum_val = current.get("shum", "0")
        fdir_val = str(fan_dir) if fan_dir is not None else current.get("f_dir", "0")
        fdir_ud_val = current.get("f_dir_ud", "0")
        fdir_lr_val = current.get("f_dir_lr", "0")

        sentinel = MODE_STEMP_SENTINEL.get(mode_str)
        if target_temp is not None:
            stemp_val = f"{target_temp:.1f}"
        elif sentinel:
            stemp_val = sentinel
        else:
            stemp_val = current.get("stemp", "22.0")

        dt_key, dh_key = MODE_TEMP_PARAMS.get(mode_num, ("dt3", "dh3"))

        params = (
            f"port={device.port}"
            f"&mode={mode_num}"
            f"&{dh_key}=0"
            f"&f_dir_ud={fdir_ud_val}"
            f"&{dt_key}={stemp_val}"
            f"&f_rate={frate_val}"
            f"&shum={shum_val}"
            f"&f_dir_lr={fdir_lr_val}"
            f"&pow={pow_val}"
            f"&stemp={stemp_val}"
        )

        _LOGGER.debug(
            "set_control -> pow=%s mode=%s(%s) stemp=%s fan=%s",
            pow_val, mode_str, mode_num, stemp_val, frate_val,
        )
        text = await self._get(f"/aircon/set_control_info?{params}")
        kv = _parse_kv(text)
        if kv.get("ret") != "OK":
            raise DaikinAPIError(f"set_control_info failed: {text[:200]}")
