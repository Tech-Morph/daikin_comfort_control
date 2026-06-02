# Daikin Comfort Control — API Documentation

> **Status:** ✅ Fully confirmed via mitmproxy traffic capture  
> **Device tested:** Daikin FTXM-series mini-split · Adapter: BRP069C4x · FW: 3.x  
> **App:** Daikin Comfort Control (Android/iOS) · HTTP client: `okhttp/4.9.2`

All endpoints, parameters, and response formats confirmed by direct traffic capture. No inferred values remain for core functionality.

---

## Base URL

```
https://scr.daikincloud.net
```

> **Note:** Earlier community assumptions pointed to `api.daikinskyport.com`. Traffic capture confirms the actual host is `scr.daikincloud.net`.

---

## Authentication

### Login

```
POST /common/login
Content-Type: application/x-www-form-urlencoded
```

**Request headers:**
```
x-daikin-uid: YOUR_DEVICE_UID
user-agent: okhttp/4.9.2
accept-encoding: gzip
```

**Request body:**

| Field | Value |
|---|---|
| `grant_type` | `password` |
| `scope` | `smart_app` |
| `username` | Your Daikin Comfort Control email |
| `password` | Your Daikin Comfort Control password |

**Response — HTTP 200, `application/json;charset=UTF-8`:**

```json
{
    "access_token":  "<hex string, ~190 chars>",
    "refresh_token": "<hex string, ~190 chars>",
    "expires_in":    "600"
}
```

| Field | Type | Notes |
|---|---|---|
| `access_token` | string | Hex string, not a JWT |
| `refresh_token` | string | Hex string, same format |
| `expires_in` | string | Always `"600"` (string, not integer) — TTL is 10 minutes |
| `token_type` | — | **Absent.** The app hardcodes the `bearer` prefix |

The server also sets a `JSESSIONID` cookie which the app ignores entirely.

---

### Token Refresh

```
POST /common/token_refresh
Content-Type: application/x-www-form-urlencoded
```

**Request headers:**
```
x-daikin-uid: YOUR_DEVICE_UID
user-agent: okhttp/4.9.2
accept-encoding: gzip
```

> ⚠️ No `authentication` header is sent for this request — only `x-daikin-uid`.

**Request body:**

| Field | Value |
|---|---|
| `grant_type` | `refresh_token` |
| `refresh_token` | Your current refresh token |

**Response — identical schema to login:**

```json
{
    "access_token":  "<new hex token>",
    "refresh_token": "<new hex token>",
    "expires_in":    "600"
}
```

**Both tokens rotate on every refresh.** Always store the new `refresh_token` from the response.

---

## Auth Headers (All Other Requests)

> ⚠️ The header name is `authentication` (non-standard — **not** the RFC `Authorization` header).

```
authentication: bearer <access_token>
x-daikin-uid: YOUR_DEVICE_UID
user-agent: okhttp/4.9.2
accept-encoding: gzip
```

`x-daikin-uid` is a static hex string tied to the Wi-Fi adapter. Find it by capturing app traffic (see [traffic-capture.md](traffic-capture.md)).

---

## Device Discovery

### List Devices

```
GET /common/device_list
```

**Confirmed response format:**
```
ret=OK,ip=<your_public_ip>,device=30050:47:0:aircon:3_1_0:1:0:0:<DeviceName>:3:polling:us:16:0:1:4:3.40:3:0::<DeviceName>:::::
```

`device` field is colon-delimited:

| Index | Example | Meaning |
|---|---|---|
| `0` | `30050` | Cloud routing port (static per device) |
| `4` | `3_1_0` | Firmware version |
| `8` | `DaikinAP07464` | Device display name |
| `11` | `us` | Region |

### Basic Info

```
GET /common/basic_info?port=<port>&lpw=&port=<port>&apw=&id=&spw=
```

Returns: `ret=OK,type=aircon,reg=us,dst=0,ver=<fw>,rev=...,mac=<mac>,...`  
Used internally to resolve the device MAC address.

---

## Aircon Control

All control endpoints return comma-separated `key=value` text. Always validate `ret=OK`.

### Get Control Info

```
GET /aircon/get_control_info?port=<port>&id=<username>&apw=&spw=
```

**Example response:**
```
ret=OK,pow=1,mode=3,stemp=20.5,shum=0,f_rate=A,f_dir=0,f_dir_ud=0,f_dir_lr=0,
dt1=22.0,dh1=0,dt2=M,dh2=0,dt3=20.5,dh3=0,dt4=25.0,dh4=0,dt6=--,dh6=0,
dfr1=A,dfr2=A,dfr3=A,dfr4=4,dfr6=A
```

### Get Sensor Info

```
GET /aircon/get_sensor_info?port=<port>&id=<username>&apw=&spw=
```

**Example response:**
```
ret=OK,htemp=21.0,hhum=--,otemp=18.5,err=0
```

`hhum` may be `--` when no humidity sensor is fitted to the adapter.

### Set Control Info

```
GET /aircon/set_control_info?port=<port>&mode=<N>&dt<N>=<stemp>&dh<N>=0&f_dir_ud=<v>&f_rate=<v>&shum=0&f_dir_lr=<v>&pow=<v>&stemp=<stemp>
```

**Cool example (mode=3):**
```
GET /aircon/set_control_info?port=30050&mode=3&dt3=20.5&f_dir_ud=0&f_rate=A&shum=0&f_dir_lr=0&pow=1&stemp=20.5&dh3=0
```

**Heat example (mode=4):**
```
GET /aircon/set_control_info?port=30050&mode=4&dh4=0&f_dir_ud=0&dt4=25.0&f_rate=4&shum=0&f_dir_lr=0&pow=1&stemp=25.0
```

**Success response:**
```
ret=OK,adv=
```

---

## Parameter Reference

### `pow`
| Value | Meaning |
|---|---|
| `0` | Off |
| `1` | On |

### `mode` — All Values Confirmed
| Value | HA HVAC Mode |
|---|---|
| `1` | `auto` |
| `2` | `dry` |
| `3` | `cool` |
| `4` | `heat` |
| `6` | `fan_only` |

### `stemp` — Target Temperature
| Value | Meaning |
|---|---|
| `20.0`, `20.5`, `25.0`, etc. | °C, 0.5° increments |
| `M` | Sentinel for dry mode |
| `--` | Sentinel for fan-only mode |

### `f_rate` — Fan Speed, All Values Confirmed
| Value | HA Fan Mode |
|---|---|
| `A` | `auto` |
| `B` | `quiet` |
| `3` | `low` |
| `4` | `medium_low` |
| `5` | `medium` |
| `6` | `medium_high` |
| `7` | `high` |

### Swing Parameters
| Parameter | Meaning |
|---|---|
| `f_dir_ud` | Up/down vane position |
| `f_dir_lr` | Left/right vane position |
| `f_dir` | Combined direction (present in `get_control_info` response) |

### Mode-Specific Temperature Parameters

Each mode stores its own last-used setpoint. The active mode’s `dtN`/`dhN` must be included in every `set_control_info` call.

| Mode | dt param | dh param |
|---|---|---|
| 1 (auto) | `dt1` | `dh1` |
| 2 (dry) | `dt2` | `dh2` |
| 3 (cool) | `dt3` | `dh3` |
| 4 (heat) | `dt4` | `dh4` |
| 6 (fan) | `dt6` | `dh6` |

---

## Port Parameter

`port=30050` appears in all device requests. This is a **cloud-side routing identifier**, not a TCP port. It is static per device and parsed from index 0 of the `device_list` response.

---

## Capture Checklist

- [x] Login request + response
- [x] Token refresh request + response (both tokens rotate)
- [x] `device_list` response format
- [x] `set_control_info` success response (`ret=OK,adv=`)
- [x] All mode values (auto=1, dry=2, cool=3, heat=4, fan_only=6)
- [x] All `f_rate` values (A, B, 3, 4, 5, 6, 7)
- [x] Swing parameters (`f_dir_ud`, `f_dir_lr`)
- [x] Token rotation confirmed

### Still Unknown
- [ ] `f_dir_ud` / `f_dir_lr` valid value ranges (swing = `S`? range 0–5?)
- [ ] Schedule/timer endpoints (if any)
- [ ] Error response format for invalid parameters
