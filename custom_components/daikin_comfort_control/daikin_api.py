"""
Daikin Comfort Control cloud API client.

Fully confirmed via mitmproxy traffic capture (2026-06-02/03):
  Base URL    : https://scr.daikincloud.net
  Login       : POST /common/login  (application/x-www-form-urlencoded)
                Body: grant_type=password&scope=smart_app&username=<u>&password=<p>
                Response: JSON {access_token, refresh_token, expires_in: "600"}
  Refresh     : POST /common/token_refresh  (application/x-www-form-urlencoded)
                Body: grant_type=refresh_token&refresh_token=<token>
                Response: identical schema to login, both tokens rotate
  Auth hdrs   : authentication: bearer <token>   <- non-standard header name
                x-daikin-uid: <static uid>
  User-Agent  : okhttp/4.9.2
  Device list : GET /common/device_list
  Poll        : GET /aircon/get_control_info?port=<port>&id=<username>&apw=&spw=
  Sensor      : GET /aircon/get_sensor_info?port=<port>&id=<username>&apw=&spw=
  Control     : GET /aircon/set_control_info?port=<port>&pow=&mode=&stemp=&...
  Success     : ret=OK,adv=
  Token TTL   : 600 s (string) -> refresh 30 s before expiry

  Confirmed modes  : auto=1, dry=2, cool=3, heat=4, fan_only=6
  Confirmed f_rate : A=auto, B=quiet, 3=low, 4=medium_low, 5=medium, 6=medium_high, 7=high
  Confirmed swing  : dfd3=0 off, dfd3=1 tilt (f_dir_ud=S), dfd3=2 lr (f_dir_lr=S), dfd3=3 both
  Sensor extras    : cmpfreq (compressor frequency Hz), mompow (compressor power draw W)
  Per-mode temps   : dt1/dt2/dt3/dt4/dt6 — must ALL be sent on every set_control call
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from .const import (
    HA_TO_DAIKIN_MODE,
    DAIKIN_TO_HA_MODE,
    HA_TO_DAIKIN_FAN,
    DAIKIN_TO_HA_FAN,
    HA_TO_DAIKIN_SWING,
    DAIKIN_TO_HA_SWING,
    SWING_OFF,
    MODE_STEMP_SENTINEL,
    MODE_TEMP_PARAMS,
)

_LOGGER = logging.getLogger(__name__)
BASE_URL = "https://scr.daikincloud.net"
_UA = "okhttp/4.9.2"

_DT_FALLBACK: dict[int, str] = {
    1: "22.0",
    2: "M",
    3: "22.0",
    4: "25.0",
    6: "--",
}


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
    fan_rate: str          # raw Daikin code: "A", "3", "B", etc.
    fan_dir: int
    swing_mode: str = SWING_OFF   # HA label: "off", "vertical", "horizontal", "both"
    cmpfreq: int = 0
    mompow: int = 0


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
            "x-daikin-uid":    self._uid,
            "user-agent":      _UA,
            "accept-encoding": "gzip",
        }
        if auth and self._access_token:
            h["authentication"] = f"bearer {self._access_token}"
        return h

    async def login(self) -> None:
        url = f"{BASE_URL}/common/login"
        payload = {
            "grant_type": "password",
            "scope":      "smart_app",
            "username":   self._username,
            "password":   self._password,
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
        self._store_tokens(data)
        _LOGGER.debug("Daikin login OK")

    async def _refresh_access_token(self) -> None:
        url = f"{BASE_URL}/common/token_refresh"
        payload = {
            "grant_type":    "refresh_token",
            "refresh_token": self._refresh_token,
        }
        try:
            async with self._session.post(
                url, data=payload, headers=self._headers(auth=False), ssl=True
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Token refresh %s, re-login", resp.status)
                    await self.login()
                    return
                data: dict[str, Any] = await resp.json(content_type=None)
        except aiohttp.ClientError:
            _LOGGER.warning("Token refresh network error, re-login")
            await self.login()
            return
        self._store_tokens(data)
        _LOGGER.debug("Daikin token refreshed")

    def _store_tokens(self, data: dict[str, Any]) -> None:
        self._access_token  = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        expires_in = int(data.get("expires_in", 600))
        self._token_expiry = time.monotonic() + expires_in - 30

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
                self._access_token = None
                await self.login()
                async with self._session.get(url, headers=self._headers(), ssl=True) as retry:
                    text = await retry.text()
                    if retry.status != 200:
                        raise DaikinAuthError(f"Still 401 after re-login on {path}")
                    return text
            if resp.status != 200:
                raise DaikinAPIError(f"HTTP {resp.status} on {path}: {text[:200]}")
            return text

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

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
            port    = fields[0]  if len(fields) > 0  else "30050"
            fw_ver  = fields[4]  if len(fields) > 4  else ""
            name    = fields[8]  if len(fields) > 8  else "DaikinAC"
            region  = fields[11] if len(fields) > 11 else ""
            basic   = await self._get_basic_info(port)
            mac     = basic.get("mac", port)
            devices.append(DaikinDevice(
                port=port, name=name, mac=mac,
                uid=self._uid, fw_ver=fw_ver, region=region,
            ))
        if not devices:
            raise DaikinAPIError(f"No devices in device_list: {text[:500]}")
        return devices

    async def _get_basic_info(self, port: str) -> dict[str, str]:
        text = await self._get(
            f"/common/basic_info?port={port}&lpw=&port={port}&apw=&id=&spw="
        )
        return _parse_kv(text)

    # ------------------------------------------------------------------
    # State polling
    # ------------------------------------------------------------------

    async def get_state_with_raw(
        self, device: DaikinDevice
    ) -> tuple[DaikinState, dict[str, str]]:
        """Return (DaikinState, raw_control_kv) — control + sensor fetched in parallel."""
        await self.ensure_token()
        ctrl, sensor = await asyncio.gather(
            asyncio.create_task(self._get_control_info(device.port)),
            asyncio.create_task(self._get_sensor_info(device.port)),
        )
        state = self._build_state(ctrl, sensor)
        return state, ctrl

    async def get_state(self, device: DaikinDevice) -> DaikinState:
        state, _ = await self.get_state_with_raw(device)
        return state

    def _build_state(
        self,
        ctrl: dict[str, str],
        sensor: dict[str, str],
    ) -> DaikinState:
        mode_num = int(ctrl.get("mode", 3))
        mode_str = DAIKIN_TO_HA_MODE.get(mode_num, "cool")

        raw_stemp = ctrl.get("stemp", "22.0")
        try:
            target_temp: float | None = (
                None if raw_stemp in ("M", "--", "") else float(raw_stemp)
            )
        except ValueError:
            target_temp = None

        # fan_rate: store as raw Daikin code so DAIKIN_TO_HA_FAN lookups work
        fan_rate = ctrl.get("f_rate", "A")

        # swing_mode: decode dfd3 -> HA label
        dfd3 = ctrl.get("dfd3", "0")
        swing_mode = DAIKIN_TO_HA_SWING.get(dfd3, SWING_OFF)

        try:
            indoor_humidity = int(float(ctrl.get("hhum") or sensor.get("hhum", 0) or 0))
        except (ValueError, TypeError):
            indoor_humidity = 0
        try:
            htemp = sensor.get("htemp", "0") or "0"
            indoor_temp = 0.0 if htemp in ("--", "") else float(htemp)
        except (ValueError, TypeError):
            indoor_temp = 0.0
        try:
            otemp = sensor.get("otemp", "0") or "0"
            outdoor_temp = 0.0 if otemp in ("--", "") else float(otemp)
        except (ValueError, TypeError):
            outdoor_temp = 0.0
        try:
            cmpfreq = int(sensor.get("cmpfreq", 0) or 0)
        except (ValueError, TypeError):
            cmpfreq = 0
        try:
            mompow = int(sensor.get("mompow", 0) or 0)
        except (ValueError, TypeError):
            mompow = 0

        return DaikinState(
            power           = ctrl.get("pow") == "1",
            mode            = mode_str,
            target_temp     = target_temp,
            indoor_temp     = indoor_temp,
            indoor_humidity = indoor_humidity,
            outdoor_temp    = outdoor_temp,
            fan_rate        = fan_rate,
            fan_dir         = int(ctrl.get("f_dir", 0) or 0),
            swing_mode      = swing_mode,
            cmpfreq         = cmpfreq,
            mompow          = mompow,
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

    # ------------------------------------------------------------------
    # Schedule inspection
    # ------------------------------------------------------------------

    async def get_schedule_info(self, device: DaikinDevice) -> dict[str, str]:
        await self.ensure_token()
        text = await self._get(
            f"/aircon/get_scdltimer_info?port={device.port}&port={device.port}"
            f"&apw=&id={self._username}&spw="
        )
        return _parse_kv(text)

    async def get_schedule_body(self, device: DaikinDevice, target: int = 1) -> dict[str, str]:
        await self.ensure_token()
        text = await self._get(
            f"/aircon/get_scdltimer_body?port={device.port}&target={target}"
            f"&port={device.port}&apw=&id={self._username}&spw=&target={target}"
        )
        return _parse_kv(text)

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def set_control(
        self,
        device: DaikinDevice,
        *,
        power: bool | None = None,
        mode: str | None = None,
        target_temp: float | None = None,
        fan_rate: str | None = None,
        fan_dir: int | None = None,
        swing_mode: str | None = None,
    ) -> None:
        """Send set_control_info to the cloud.

        swing_mode: HA label ("off", "vertical", "horizontal", "both").
        Automatically resolves to the correct dfd3/f_dir_ud/f_dir_lr triplet.
        """
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

        # Swing: if caller specifies swing_mode use that, else carry forward current
        if swing_mode is not None:
            dfd3_val, fdir_ud_val, fdir_lr_val = HA_TO_DAIKIN_SWING.get(
                swing_mode, ("0", "0", "0")
            )
        else:
            dfd3_val    = current.get("dfd3",    "0")
            fdir_ud_val = current.get("f_dir_ud", "0")
            fdir_lr_val = current.get("f_dir_lr", "0")

        # stemp for the active mode
        sentinel = MODE_STEMP_SENTINEL.get(mode_str)
        if target_temp is not None:
            stemp_val = f"{target_temp:.1f}"
        elif sentinel:
            stemp_val = sentinel
        else:
            stemp_val = current.get("stemp", "22.0")

        # Per-mode dt values — carry forward all, update active mode only
        dt_vals: dict[int, str] = {}
        for m, (dt_name, _) in MODE_TEMP_PARAMS.items():
            if m == mode_num:
                dt_vals[m] = stemp_val
            else:
                dt_vals[m] = current.get(dt_name) or _DT_FALLBACK.get(m, "22.0")

        params = (
            f"port={device.port}"
            f"&mode={mode_num}"
            f"&dh1=0&dh2=0&dh3=0&dh4=0&dh6=0"
            f"&f_dir_ud={fdir_ud_val}"
            f"&dt1={dt_vals[1]}"
            f"&dt2={dt_vals[2]}"
            f"&dt3={dt_vals[3]}"
            f"&dt4={dt_vals[4]}"
            f"&dt6={dt_vals[6]}"
            f"&f_rate={frate_val}"
            f"&shum={shum_val}"
            f"&f_dir_lr={fdir_lr_val}"
            f"&pow={pow_val}"
            f"&stemp={stemp_val}"
            f"&dfd3={dfd3_val}"
        )

        _LOGGER.debug(
            "set_control -> pow=%s mode=%s(%s) stemp=%s fan=%s swing=%s(dfd3=%s ud=%s lr=%s)",
            pow_val, mode_str, mode_num, stemp_val, frate_val,
            swing_mode, dfd3_val, fdir_ud_val, fdir_lr_val,
        )

        text = await self._get(f"/aircon/set_control_info?{params}")
        kv = _parse_kv(text)
        if kv.get("ret") != "OK":
            raise DaikinAPIError(f"set_control_info failed: {text[:200]}")
