# Daikin Comfort Control — Home Assistant Custom Integration

A HACS-compatible Home Assistant custom integration for **Daikin mini-split units** using the **BRP069C4x Wi-Fi adapter on firmware 3.x**, controlled via the Daikin Comfort Control North American cloud (`scr.daikincloud.net`).

> **Why does this exist?** The local REST API (port 80, `/aircon/get_control_info`) was removed in BRP069C4x firmware 3.x. The HTTPS local API (port 443) connects but returns empty bodies. This integration reverse-engineered the official Daikin Comfort Control iOS/Android app to communicate with the cloud API directly.

---

## Tested Hardware

| Component | Value |
|---|---|
| AC Unit | Daikin FTXM12WVJU9 (12,000 BTU mini-split) |
| Wi-Fi Adapter | BRP069C4x |
| Adapter Firmware | 3.1.0 |
| Cloud | `scr.daikincloud.net` (Daikin Skyport North America) |
| HA Platform | Home Assistant OS (HAOS) on Proxmox |

---

## Features

- ✅ On/Off control
- ✅ HVAC modes: Auto, Cool, Heat, Dry, Fan Only
- ✅ Target temperature (0.5°C steps, 10–32°C)
- ✅ Fan speed: Auto, Night, Quiet, Low, Medium Low, Medium, Medium High, High, Powerful
- ✅ Current indoor temperature & humidity sensor
- ✅ Outdoor temperature in extra state attributes
- ✅ Automatic token refresh (10-min token, refresh without re-login)
- ✅ Configurable poll interval (default 30s, min 10s)
- ✅ Full config flow UI — no YAML required
- ✅ Options flow to adjust poll interval without re-adding

---

## How It Works

### The Problem

Daikin's BRP069C4x adapter running firmware 3.x removed the documented local REST API. The device communicates exclusively with Daikin's North American cloud using a proprietary protocol — not the EU Daikin Onecta API.

### Reverse Engineering Methodology

Traffic was captured from the official Daikin Comfort Control Android app using **mitmproxy in WireGuard mode** with **Frida gadget SSL unpinning** to bypass certificate pinning.

**Toolchain used:**
- `mitmproxy` (WireGuard transparent proxy mode)
- `frida-tools` + custom SSL bypass script injected via Frida gadget APK
- Android device connected via WireGuard tunnel to Linux host running mitmweb

**Capture process:**
1. Patch the Daikin APK with Frida gadget to disable SSL certificate pinning
2. Run `mitmweb --mode wireguard` on the Linux host
3. Connect the Android device through the WireGuard tunnel
4. Interact with the app — login, device list, state polling, control commands
5. All HTTPS traffic to `scr.daikincloud.net` is captured in plaintext

### Discovered API

**Base URL:** `https://scr.daikincloud.net`

All authenticated requests require these headers:
```
authentication: bearer <access_token>
x-daikin-uid: <device_uid>
user-agent: okhttp/4.9.2
```

> **Note:** The header is `authentication` (lowercase, non-standard) — **not** `Authorization`.

#### Authentication

```
POST /common/login
Content-Type: application/x-www-form-urlencoded

grant_type=password&scope=smart_app&username=<email>&password=<password>
```

Response:
```json
{
  "access_token": "<hex>",
  "refresh_token": "<hex>",
  "expires_in": "600"
}
```

Token expiry is **600 seconds (10 minutes)**. The integration refreshes using:

```
POST /common/token_refresh
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh_token>
```

> No `authentication` or `x-daikin-uid` headers on this endpoint.

#### Device List

```
GET /common/device_list
```

Returns a CSV-like string:
```
ret=OK,ip=<wan_ip>,device=<port>:<fields...>
```

Device fields (colon-separated): `port:?:?:type:firmware:...:name:...:method:region:...`

#### State Polling

```
GET /aircon/get_control_info?port=30050&lpw=&port=30050&apw=&id=<username>&spw=
GET /aircon/get_sensor_info?port=30050&lpw=&port=30050&apw=&id=<username>&spw=
```

Control info response fields:

| Field | Description |
|---|---|
| `pow` | Power state (0=off, 1=on) |
| `mode` | 1=auto, 2=dry, 3=cool, 4=heat, 6=fan_only |
| `stemp` | Set temperature in °C (`M` for dry mode) |
| `f_rate` | Fan speed (A=auto, B=night, 1–5=low→high, 6=quiet, 7=powerful) |
| `f_dir_ud` | Vertical swing (0=fixed) |
| `f_dir_lr` | Horizontal swing (0=fixed) |

Sensor info response: `htemp` (indoor °C), `hhum` (indoor humidity %), `otemp` (outdoor °C)

#### Control

```
GET /aircon/set_control_info?port=30050&mode=<n>&dt<n>=<temp>&f_dir_ud=0
    &f_rate=<rate>&dfr<n>=<rate>&shum=0&f_dir_lr=0&pow=<0|1>&stemp=<temp>&dh<n>=0
```

Key points:
- **GET request** (not POST) with all params in the query string
- `dt<n>` and `dh<n>` are **mode-indexed**: the digit matches the mode number (e.g. `dt3=18.0` for cool mode=3)
- Dry mode uses `stemp=M&dt2=M` instead of a numeric temperature
- `dfr<n>` mirrors `f_rate` for the active mode

Successful response: `ret=OK,adv=`

### The `x-daikin-uid`

This is a **static app installation identifier** generated when the Daikin Comfort Control app is first installed. It is sent on every request including login. It is **not** derived from the device MAC address. You capture it once via mitmproxy and store it in the integration config. It only changes if the app is reinstalled.

---

## Installation

### Prerequisites

- Home Assistant OS (or any HA install with custom component support)
- HACS installed (optional but recommended)
- Your Daikin Comfort Control account credentials (email + password)
- Your `x-daikin-uid` value (see below)

### Getting Your UID

The `x-daikin-uid` must be captured once from the official Daikin Comfort Control app using a network proxy. The simplest approach:

1. Install [mitmproxy](https://mitmproxy.org/) on a Linux machine
2. Run: `mitmweb --mode wireguard --ssl-insecure`
3. Connect your phone through the WireGuard tunnel
4. Open the Daikin Comfort Control app and log in
5. Look for the `x-daikin-uid` header on the `POST /common/login` request

> If the app shows a certificate error, you need to bypass SSL pinning using Frida. See the [Traffic Capture Guide](docs/traffic-capture.md) (coming soon).

### Manual Installation

```bash
# Copy the integration to your HA config directory
cp -r custom_components/daikin_comfort_control \
    /path/to/homeassistant/config/custom_components/
```

### HACS Installation

1. In HACS → Integrations → ⋮ → Custom Repositories
2. Add: `https://github.com/Tech-Morph/daikin_comfort_control`
3. Category: Integration
4. Install "Daikin Comfort Control"

### Adding to Home Assistant

1. **Settings → Devices & Services → Add Integration**
2. Search for **"Daikin Comfort Control"**
3. Enter:
   - **Username:** your Daikin Comfort Control email
   - **Password:** your password
   - **UID:** your `x-daikin-uid` value
4. Submit — HA will authenticate, discover your device, and create a climate entity

### Options

After setup, click **Configure** on the integration to adjust:
- **Scan interval** (10–300 seconds, default 30)

---

## File Structure

```
custom_components/daikin_comfort_control/
├── __init__.py        # Integration setup, entry load/unload
├── manifest.json      # Integration metadata
├── const.py           # Constants, mode/fan mappings
├── config_flow.py     # UI config flow + options flow
├── coordinator.py     # DataUpdateCoordinator, polling logic
├── climate.py         # ClimateEntity implementation
└── daikin_api.py      # Async API client (login, poll, control)
```

---

## Known Limitations

- **Cloud-dependent:** No local API exists on firmware 3.x. If `scr.daikincloud.net` is unreachable, the integration will be unavailable.
- **Single device:** Currently discovers the first device on the account. Multi-device support is planned.
- **Temperature units:** The API returns Celsius only. Fahrenheit conversion is handled by HA automatically.
- **UID required:** The `x-daikin-uid` must be captured manually. There is no known way to derive it programmatically without running the official app.

---

## Disclaimer

This integration was developed by reverse engineering network traffic from the official Daikin Comfort Control app for personal home automation use. It is not affiliated with or endorsed by Daikin. Use at your own risk. The cloud API is undocumented and may change without notice.
