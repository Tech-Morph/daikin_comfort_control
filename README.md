# Daikin Comfort Control — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A HACS-compatible custom integration for controlling **Daikin mini-split units** via the Daikin Comfort Control cloud (North American Skyport platform). Targeted at BRP069C4x Wi-Fi adapters on firmware 3.x, where the local REST API was removed. All control goes through `https://scr.daikincloud.net`.

> **Status:** Beta — all core API values confirmed via mitmproxy traffic capture. Tested against Daikin FTXM-series units with BRP069C4x adapter on FW 3.x.

---

## Features

- ✅ Email/password authentication via Daikin cloud
- ✅ Automatic token refresh (10-minute TTL, both tokens rotate)
- ✅ Climate entity per device: on/off, HVAC mode, target temperature, fan speed
- ✅ Sensors per device: indoor temp, outdoor temp, indoor humidity, fan speed, fan direction
- ✅ Configurable poll interval (default 30s)
- ✅ Config flow UI — no YAML required
- ✅ HACS compatible

---

## Want Autonomous Climate Control?

This integration handles the connection to your Daikin unit, but it does not decide *when* to change temperature, mode, or fan speed on its own — that's manual or automation-driven.

For fully autonomous, self-adjusting climate control built on top of this integration, check out **[Daikin-Smart-Temperature](https://github.com/Tech-Morph/Daikin-Smart-Temperature)**:

- Reads `htemp`/`otemp` directly from this integration's coordinator — no extra sensors or hardware required
- Automatically switches between cool, heat, and fan-only based on live indoor temperature vs. your target
- Time-of-day learning offsets (morning/day/evening/night) so comfort adjusts throughout the day
- Season-aware heating logic — e.g., suppress heat in summer unless it's actually cold outside and only at night
- Outdoor-trend pre-cooling — tightens response before afternoon heat spikes hit
- Manual override detection — pauses automation if you adjust the AC directly, then resumes automatically
- Configurable safety rails: min/max temp, allowed HVAC modes, max fan speed, mode-switch cooldown

Install **Daikin Comfort Control** (this repo) first, then add **Daikin-Smart-Temperature** on top — it will auto-detect any devices configured here.

---

## Entities Created Per Device

### Climate
| Entity | Domain |
|---|---|
| `climate.<device>` | `climate` |

### Sensors
| Entity | Unit | Notes |
|---|---|---|
| `sensor.<device>_outdoor_temperature` | °F / °C | Auto-converted to your HA unit system |
| `sensor.<device>_indoor_temperature` | °F / °C | Auto-converted to your HA unit system |
| `sensor.<device>_indoor_humidity` | % | `unavailable` if adapter has no humidity sensor |
| `sensor.<device>_fan_speed` | — | auto / quiet / low / medium_low / medium / medium_high / high |
| `sensor.<device>_fan_direction` | — | stopped / swing / position_1–5 |

---

## Supported HVAC Modes
| HA Mode | Daikin `mode=` |
|---|---|
| Cool | `3` |
| Heat | `4` |
| Auto | `1` |
| Dry | `2` |
| Fan Only | `6` |

## Fan Speeds
| HA Fan Mode | Daikin `f_rate=` |
|---|---|
| Auto | `A` |
| Quiet | `B` |
| Low | `3` |
| Medium Low | `4` |
| Medium | `5` |
| Medium High | `6` |
| High | `7` |

---

## Installation

### Via HACS (Recommended)
1. In HA: **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/Tech-Morph/daikin_comfort_control` as type **Integration**
3. Install **Daikin Comfort Control**
4. Restart Home Assistant

### Manual
```bash
cp -r custom_components/daikin_comfort_control \
  /config/custom_components/daikin_comfort_control
# restart Home Assistant
```

---

## Configuration

1. **Settings → Devices & Services → Add Integration**
2. Search for **Daikin Comfort Control**
3. Fill in the form:

| Field | Description |
|---|---|
| **Email address** | Your Daikin Comfort Control app login email |
| **Password** | Your Daikin Comfort Control app password |
| **Device UID** | The `x-daikin-uid` value from a traffic capture (see below) |
| **Poll interval** | Seconds between state updates (default: 30, min: 10, max: 300) |

### Finding Your Device UID

The UID is a static 32-character hex string tied to your Wi-Fi adapter hardware. It appears as the `x-daikin-uid` header in every request the app makes to `scr.daikincloud.net`. Capture it once using mitmproxy — see [docs/traffic-capture.md](docs/traffic-capture.md) for step-by-step instructions.

Example format (placeholder): x-daikin-uid: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx


---

## Confirmed API Behavior

| Item | Value |
|---|---|
| Base URL | `https://scr.daikincloud.net` |
| Auth endpoint | `POST /common/login` (form-encoded) |
| Token refresh | `POST /common/token_refresh` (no auth header required, only `x-daikin-uid`) |
| Token format | Hex string ~190 chars (not JWT) |
| Token TTL | `"600"` seconds (string) = 10 minutes |
| Token rotation | Both `access_token` and `refresh_token` rotate on every refresh |
| Auth header | `authentication: bearer <token>` *(non-standard header name)* |
| Control read | `GET /aircon/get_control_info` |
| Control write | `GET /aircon/set_control_info` |
| Success response | `ret=OK,adv=<value>` |
| Response format | Comma-separated `key=value` (not JSON) |

See [docs/api_docs.md](docs/api_docs.md) for the complete API reference.

---

## Development

### Project Structure

custom_components/daikin_comfort_control/
├── _init_.py # Entry point, setup/unload
├── manifest.json # Integration metadata
├── const.py # All confirmed mode/fan/parameter mappings
├── daikin_api.py # Async cloud API client (aiohttp)
├── coordinator.py # DataUpdateCoordinator
├── config_flow.py # UI config flow
├── climate.py # Climate platform entity
├── sensor.py # Sensor platform (5 sensors per device)
├── strings.json # UI strings
├── brand/ # Icon/logo for HA frontend (2026.3+)
└── translations/
└── en.json

docs/
├── api_docs.md # Complete confirmed API reference
└── traffic-capture.md # mitmproxy setup guide

### Debug Logging
```yaml
logger:
  default: warning
  logs:
    custom_components.daikin_comfort_control: debug
```

---

## Troubleshooting

**"No devices found"** — Check that the Device UID matches the `x-daikin-uid` from your traffic capture.

**"Cannot connect"** — Verify your HA instance has outbound HTTPS access to `scr.daikincloud.net`.

**"Invalid auth"** — Confirm your credentials work in the Daikin Comfort Control app directly.

**Sensors show `unavailable`** — Normal on first load. They populate after the first successful poll. Humidity will remain `unavailable` if your adapter model has no humidity sensor.

**Temperature shows in wrong unit** — The integration reports in °C natively; HA converts to your configured unit system automatically. Check **Settings → System → General → Unit system**.
