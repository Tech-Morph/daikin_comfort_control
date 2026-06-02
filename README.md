# Daikin Comfort Control — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A HACS-compatible custom integration for controlling **Daikin mini-split units** via the Daikin Comfort Control cloud (North American Skyport platform).

Targeted at BRP069C4x Wi-Fi adapters on firmware 3.x, where the local REST API was removed. All control goes through `https://scr.daikincloud.net`.

> **Status:** Beta — all core API values confirmed via mitmproxy traffic capture. Tested against Daikin FTXM12WVJU9 with BRP069C4x adapter (FW 3.1.0).

---

## Features

- ✅ Email/password authentication via Daikin cloud
- ✅ Automatic token refresh (600s TTL, both tokens rotate)
- ✅ Climate entity per device: on/off, HVAC mode, target temperature, fan speed
- ✅ Outdoor temperature exposed as extra state attribute
- ✅ Configurable poll interval (default 30s)
- ✅ Config flow UI — no YAML required
- ✅ HACS compatible

---

## Supported Modes

All mode values confirmed via traffic capture.

| HA Mode | Daikin `mode=` |
|---|---|
| Cool | `3` |
| Heat | `4` |
| Auto | `1` |
| Dry | `2` |
| Fan Only | `6` |

## Fan Speeds

All `f_rate` values confirmed via traffic capture.

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

## Confirmed API Behavior

| Item | Confirmed Value |
|---|---|
| Base URL | `https://scr.daikincloud.net` |
| Auth endpoint | `POST /common/login` (form-encoded) |
| Token refresh | `POST /common/token_refresh` (no auth header, just x-daikin-uid) |
| Token format | Hex string ~190 chars (not JWT) |
| Token TTL | `"600"` (string) = 10 minutes |
| Token rotation | Both `access_token` and `refresh_token` rotate on every refresh |
| Auth header | `authentication: bearer <token>` *(non-standard name)* |
| Control read | `GET /aircon/get_control_info?port=30050&id=<user>` |
| Control write | `GET /aircon/set_control_info?port=30050&...` |
| Success response | `ret=OK,adv=` |
| Response format | Comma-separated `key=value` (not JSON) |
| Swing params | `f_dir_ud` (up/down), `f_dir_lr` (left/right) |

See [docs/api_docs.md](docs/api_docs.md) for the complete API reference.

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
```

Restart HA.

---

## Configuration

1. **Settings → Devices & Services → Add Integration**
2. Search for **Daikin Comfort Control**
3. Enter:
   - **Email** — your Daikin Comfort Control app login
   - **Password** — your Daikin Comfort Control app password
   - **Device UID** — the `x-daikin-uid` value from a mitmproxy capture (see below)
   - **Poll interval** — seconds between state updates (default: 30)

### Finding Your Device UID

The UID is a static hex string tied to your Wi-Fi adapter, present in every API request as the `x-daikin-uid` header. Capture it using mitmproxy:

```
x-daikin-uid: dcd2e719644c4716afc1f729e98b609c
```

See [docs/traffic-capture.md](docs/traffic-capture.md) for the full mitmproxy setup guide.

---

## Development

### Project Structure

```
custom_components/daikin_comfort_control/
├── __init__.py        # Entry point, setup/unload
├── manifest.json      # Integration metadata
├── const.py           # Constants, confirmed mode/fan mappings
├── daikin_api.py      # Cloud API client (aiohttp)
├── coordinator.py     # DataUpdateCoordinator
├── config_flow.py     # UI config flow
├── climate.py         # Climate platform entity
├── strings.json       # UI strings
└── translations/
    └── en.json

docs/
├── api_docs.md        # Complete confirmed API documentation
└── traffic-capture.md # mitmproxy setup guide
```

### Capture → Implement Workflow

1. Capture traffic with mitmproxy (see [docs/traffic-capture.md](docs/traffic-capture.md))
2. Document findings in [docs/api_docs.md](docs/api_docs.md)
3. Update code with confirmed values
4. Test via **Developer Tools → Template** before UI testing

---

## Troubleshooting

**"No devices found"** — Check that the device UID matches the `x-daikin-uid` from your capture.

**"Cannot connect"** — Verify your HA instance has outbound HTTPS to `scr.daikincloud.net`.

**"Invalid auth"** — Confirm credentials work in the Daikin Comfort Control app directly.

**Enable debug logging:**
```yaml
logger:
  default: warning
  logs:
    custom_components.daikin_comfort_control: debug
```

---

## Contributing

All core API values are now confirmed. Outstanding unknowns: `f_dir_ud`/`f_dir_lr` valid value ranges, schedule/timer endpoints, and error response format for invalid params. See [docs/api_docs.md](docs/api_docs.md) for the full checklist.
