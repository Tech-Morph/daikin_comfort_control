from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass
import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://scr.daikincloud.net"

HVAC_MODES = {"auto": 1, "dry": 2, "cool": 3, "heat": 4, "fan_only": 6}
HVAC_MODES_REV = {v: k for k, v in HVAC_MODES.items()}

FAN_RATES = {"auto": "A", "night": "B", "quiet": "6", "low": "1",
             "medium_low": "2", "medium": "3", "medium_high": "4",
             "high": "5", "powerful": "7"}
FAN_RATES_REV = {v: k for k, v in FAN_RATES.items()}


def _parse_kv(text: str) -> dict[str, str]:
    result = {}
    for pair in text.strip().split(","):
        if "=" in pair:
            k, _, v = pair.partition("=")
            result[k.strip()] = v.strip()
    return result


@dataclass
class DaikinDevice:
    port: str
    name: str
    mac: str
    uid: str       # x-daikin-uid (hardcoded per device install, not MAC-derived)
    fw_ver: str


@dataclass
class DaikinState:
    power: bool
    mode: str
    target_temp: float | None
    indoor_temp: float
    indoor_humidity: int
    outdoor_temp: float
    fan_rate: str
    fan_dir_ud: int
    fan_dir_lr: int


class DaikinAuthError(Exception):
    pass

class DaikinAPIError(Exception):
    pass


class DaikinCloudClient:
    def __init__(self, username: str, password: str, uid: str, session: aiohttp.ClientSession):
        self._username = username
        self._password = password
        self._uid = uid  # x-daikin-uid — stored from first login capture or config
        self._session = session
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: float = 0
        self._device: DaikinDevice | None = None

    def _headers(self, include_auth: bool = True) -> dict[str, str]:
        h = {
            "x-daikin-uid": self._uid,
            "user-agent": "okhttp/4.9.2",
            "accept-encoding": "gzip",
        }
        if include_auth and self._access_token:
            h["authentication"] = f"bearer {self._access_token}"
        return h

    async def login(self) -> None:
        url = f"{BASE_URL}/common/login"
        data = {
            "grant_type": "password",
            "scope": "smart_app",
            "username": self._username,
            "password": self._password,
        }
        async with self._session.post(url, data=data, headers=self._headers(include_auth=False), ssl=False) as resp:
            if resp.status != 200:
                raise DaikinAuthError(f"Login failed: HTTP {resp.status}")
            body = await resp.json(content_type=None)

        self._access_token = body["access_token"]
        self._refresh_token = body["refresh_token"]
        self._token_expiry = time.time() + int(body.get("expires_in", 600)) - 30
        _LOGGER.info("Daikin login OK, token valid for ~%ss", body.get("expires_in"))

    async def _refresh_access_token(self) -> None:
        url = f"{BASE_URL}/common/token_refresh"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }
        # No authentication or x-daikin-uid on this endpoint
        headers = {"user-agent": "okhttp/4.9.2", "content-type": "application/x-www-form-urlencoded; charset=utf-8"}
        async with self._session.post(url, data=data, headers=headers, ssl=False) as resp:
            if resp.status != 200:
                _LOGGER.warning("Token refresh failed (%s), falling back to re-login", resp.status)
                await self.login()
                return
            body = await resp.json(content_type=None)

        self._access_token = body["access_token"]
        self._refresh_token = body["refresh_token"]
        self._token_expiry = time.time() + int(body.get("expires_in", 600)) - 30
        _LOGGER.debug("Token refreshed OK")

    async def ensure_token(self) -> None:
        if time.time() >= self._token_expiry:
            if self._refresh_token:
                await self._refresh_access_token()
            else:
                await self.login()

    async def _get(self, path: str) -> str:
        async with self._session.get(
            f"{BASE_URL}{path}", headers=self._headers(), ssl=False
        ) as resp:
            text = await resp.text()
            if resp.status == 401:
                raise DaikinAuthError("Unauthorized")
            if resp.status != 200:
                raise DaikinAPIError(f"HTTP {resp.status}: {text}")
            return text

    # ---- Device discovery ----

    async def get_devices(self) -> list[DaikinDevice]:
        await self.ensure_token()
        text = await self._get("/common/device_list")
        kv = _parse_kv(text)
        if kv.get("ret") != "OK":
            raise DaikinAPIError(f"device_list: {text}")

        fields = kv.get("device", "").split(":")
        port  = fields[0] if fields else "30050"
        name  = fields[8] if len(fields) > 8 else "DaikinAC"

        # Get MAC from basic_info
        basic = await self._get_basic_info(port, id_param="")
        mac = basic.get("mac", "")

        device = DaikinDevice(port=port, name=name, mac=mac, uid=self._uid, fw_ver=basic.get("ver", ""))
        self._device = device
        return [device]

    async def _get_basic_info(self, port: str, id_param: str | None = None) -> dict[str, str]:
        uid = id_param if id_param is not None else self._username
        text = await self._get(f"/common/basic_info?port={port}&lpw=&port={port}&apw=&id={uid}&spw=")
        return _parse_kv(text)

    # ---- State polling ----

    async def get_state(self, device: DaikinDevice) -> DaikinState:
        await self.ensure_token()
        ctrl_task   = asyncio.create_task(self._get_control_info(device.port))
        sensor_task = asyncio.create_task(self._get_sensor_info(device.port))
        ctrl, sensor = await asyncio.gather(ctrl_task, sensor_task)

        mode_num = int(ctrl.get("mode", 3))
        raw_stemp = ctrl.get("stemp", "22.0")
        target_temp = None if raw_stemp == "M" else float(raw_stemp)

        return DaikinState(
            power=ctrl.get("pow") == "1",
            mode=HVAC_MODES_REV.get(mode_num, "cool"),
            target_temp=target_temp,
            indoor_temp=float(sensor.get("htemp", 0)),
            indoor_humidity=int(sensor.get("hhum", 0)),
            outdoor_temp=float(sensor.get("otemp", 0)),
            fan_rate=FAN_RATES_REV.get(ctrl.get("f_rate", "A"), "auto"),
            fan_dir_ud=int(ctrl.get("f_dir_ud", 0)),
            fan_dir_lr=int(ctrl.get("f_dir_lr", 0)),
        )

    async def _get_control_info(self, port: str) -> dict[str, str]:
        text = await self._get(
            f"/aircon/get_control_info?port={port}&lpw=&port={port}&apw=&id={self._username}&spw="
        )
        return _parse_kv(text)

    async def _get_sensor_info(self, port: str) -> dict[str, str]:
        text = await self._get(
            f"/aircon/get_sensor_info?port={port}&lpw=&port={port}&apw=&id={self._username}&spw="
        )
        return _parse_kv(text)

    # ---- Control ----

    async def set_control(
        self,
        device: DaikinDevice,
        power: bool | None = None,
        mode: str | None = None,
        target_temp: float | None = None,
        fan_rate: str | None = None,
    ) -> None:
        await self.ensure_token()
        current = await self._get_control_info(device.port)

        pow_val   = ("1" if power else "0") if power is not None else current.get("pow", "0")
        mode_str  = mode or HVAC_MODES_REV.get(int(current.get("mode", 3)), "cool")
        mode_num  = HVAC_MODES.get(mode_str, 3)
        frate_val = FAN_RATES.get(fan_rate, current.get("f_rate", "A")) if fan_rate else current.get("f_rate", "A")
        fud_val   = current.get("f_dir_ud", "0")
        flr_val   = current.get("f_dir_lr", "0")
        shum_val  = current.get("shum", "0")

        # Mode-indexed temp/hum params: dt<mode> and dh<mode>
        # Dry mode uses M for temp
        if mode_str == "dry":
            stemp_val = "M"
            dt_val    = "M"
        else:
            stemp_val = str(target_temp) if target_temp is not None else current.get("stemp", "22.0")
            dt_val    = stemp_val

        dh_val = "0"

        params = (
            f"port={device.port}"
            f"&mode={mode_num}"
            f"&dt{mode_num}={dt_val}"
            f"&f_dir_ud={fud_val}"
            f"&f_rate={frate_val}"
            f"&dfr{mode_num}={frate_val}"
            f"&shum={shum_val}"
            f"&f_dir_lr={flr_val}"
            f"&pow={pow_val}"
            f"&stemp={stemp_val}"
            f"&dh{mode_num}={dh_val}"
        )

        text = await self._get(f"/aircon/set_control_info?{params}")
        kv = _parse_kv(text)
        if kv.get("ret") != "OK":
            raise DaikinAPIError(f"set_control_info failed: {text}")
        _LOGGER.debug("set_control_info OK → pow=%s mode=%s stemp=%s f_rate=%s", pow_val, mode_num, stemp_val, frate_val)
