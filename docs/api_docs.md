# Daikin Comfort Control — API Documentation

> **Status:** Confirmed via mitmproxy traffic capture · 2026-06-02  
> **Device:** Daikin FTXM12WVJU9 · Adapter: BRP069C4x · FW: 3.1.0  
> **App:** Daikin Comfort Control (Android) · `okhttp/4.9.2`

---

## Base URL

```
https://scr.daikincloud.net
```

> Note: Earlier assumptions pointed to `api.daikinskyport.com`. Traffic capture confirmed the actual host is `scr.daikincloud.net`.

---

## Authentication

### Login

```
POST /common/login
Content-Type: application/x-www-form-urlencoded
```

**Request body:**

| Field | Value |
|---|---|
| `grant_type` | `password` |
| `scope` | `smart_app` |
| `username` | Daikin account email |
| `password` | Daikin account password |

**Required headers (no auth token needed for login):**

```
x-daikin-uid: <device-uid>
user-agent: okhttp/4.9.2
accept-encoding: gzip
```

**Response — HTTP 200, `application/json;charset=UTF-8`:**

```json
{
    "access_token":  "8890d3da1a576428aa5f4404721586e8...",
    "refresh_token": "4e3f72cb9a7d757b5131613fda2b5c05...",
    "expires_in":    "600"
}
```

**Confirmed response details (2026-06-02):**

| Field | Type | Notes |
|---|---|---|
| `access_token` | string | Hex string, ~190 chars. **Not a JWT** (no `.` separators). |
| `refresh_token` | string | Hex string, ~190 chars. Same format as access token. |
| `expires_in` | string | `"600"` — returned as a **string**, not an integer. Token TTL = 10 minutes. |
| `token_type` | — | **Field is absent.** The app hardcodes the `bearer` prefix. |

**Server also sets a session cookie** (`JSESSIONID`) but the app ignores it entirely — all auth is via the bearer token header.

### Token Refresh

```
POST /common/token_refresh
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<token>
```

Falls back to full re-login if this endpoint returns non-200.

---

## Auth Headers (All Subsequent Requests)

> ⚠️ The authentication header uses the non-standard name `authentication` (not `Authorization`).

```
authentication: bearer <access_token>
x-daikin-uid: <device-uid>
user-agent: okhttp/4.9.2
accept-encoding: gzip
```

The `x-daikin-uid` is a static hex string tied to the adapter, captured from mitmproxy as `dcd2e719644c4716afc1f729e98b609c`.

---

## Device Discovery

### List Devices

```
GET /common/device_list
```

Returns a comma-separated key=value string. The `device` field contains colon-separated subfields.
Field index 0 = port, field index 8 = device name.

### Basic Info

```
GET /common/basic_info?port=<port>&lpw=&port=<port>&apw=&id=&spw=
```

Returns `ret=OK,type=aircon,reg=us,dst=0,ver=<fw>,rev=...,mac=<mac>,...`

---

## Aircon Control

All control endpoints return comma-separated `key=value` pairs. Always check `ret=OK`.

### Get Control Info

```
GET /aircon/get_control_info?port=<port>&id=<username>&apw=&spw=
```

**Example response:**
```
ret=OK,pow=1,mode=3,stemp=20.5,shum=0,f_rate=A,f_dir=0,f_dir_ud=0,f_dir_lr=0,dt1=22.0,dh1=0,dt2=M,dh2=0,dt3=20.5,dh3=0,dt6=--,dh6=0,dt7=22.0,dh7=0,dfr1=A,dfr2=A,dfr3=A,dfr6=A,dfr7=A
```

### Get Sensor Info

```
GET /aircon/get_sensor_info?port=<port>&id=<username>&apw=&spw=
```

**Example response:**
```
ret=OK,htemp=21.0,hhum=--,otemp=18.5,err=0
```

### Set Control Info

```
GET /aircon/set_control_info?port=<port>&pow=<pow>&mode=<mode>&stemp=<stemp>&shum=<shum>&f_rate=<f_rate>&f_dir=<f_dir>&dt<N>=<stemp>&dh<N>=0&dfr<N>=<f_rate>
```

**Confirmed from capture:**
```
GET /aircon/set_control_info?port=30050&mode=3&dt3=20.5&f_dir_ud=0&f_rate=A&shum=0&f_dir_lr=0&pow=1&stemp=20.5&dh3=0
```

---

## Parameter Reference

### `pow`
| Value | Meaning |
|---|---|
| `0` | Off |
| `1` | On |

### `mode`
| Value | HA Mode | Notes |
|---|---|---|
| `1` | `auto` | Inferred |
| `2` | `dry` | Inferred |
| `3` | `cool` | **Confirmed in capture** |
| `6` | `fan_only` | Inferred |
| `7` | `heat` | Inferred |

> Modes 1, 2, 6, 7 follow standard BRP069C convention and have not yet been independently confirmed via capture. Test each mode and update this table.

### `stemp` — Target Temperature
| Value | Meaning |
|---|---|
| `20.5`, `20.0`, etc. | Temperature in °C (0.5° increments) |
| `M` | Sentinel for dry mode |
| `--` | Sentinel for fan-only mode |

### `f_rate` — Fan Speed
| Value | HA Fan Mode | Notes |
|---|---|---|
| `A` | `auto` | **Confirmed in capture** |
| `B` | `quiet` | Inferred |
| `3` | `low` | Inferred |
| `4` | `medium_low` | Inferred |
| `5` | `medium` | Inferred |
| `6` | `medium_high` | Inferred |
| `7` | `high` | Inferred |

### Mode-Specific Parameters

Each mode uses a dedicated temperature/humidity/fan-rate parameter set:

| Mode | dt param | dh param | dfr param |
|---|---|---|---|
| 1 (auto) | `dt1` | `dh1` | `dfr1` |
| 2 (dry) | `dt2` | `dh2` | `dfr2` |
| 3 (cool) | `dt3` | `dh3` | `dfr3` |
| 6 (fan) | `dt6` | `dh6` | `dfr6` |
| 7 (heat) | `dt7` | `dh7` | `dfr7` |

---

## Port

All device endpoints require a `port=` query parameter. The port value `30050` was confirmed in all captured requests. This appears to be a static routing identifier within the Daikin cloud proxy, not a TCP port.

---

## What Still Needs Capture

- [x] Login response body — ✅ confirmed 2026-06-02
- [ ] `device_list` response body (confirm field structure, number of devices)
- [ ] `set_control_info` response body (confirm `ret=OK` format)
- [ ] Mode changes: heat, auto, dry, fan_only (confirm mode values 1, 2, 6, 7)
- [ ] Manual fan speed selection (confirm `f_rate` numeric values 3–7)
- [ ] `f_dir` / `f_dir_ud` / `f_dir_lr` swing parameter behavior
- [ ] Token refresh endpoint and response format
- [ ] Any schedule/timer endpoints
