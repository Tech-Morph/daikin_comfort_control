# Daikin Comfort Control — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A HACS-compatible custom integration for controlling **Daikin mini-split units** via the Daikin Comfort Control cloud (North American Skyport platform).

Targeted at BRP069C4x Wi-Fi adapters on firmware 3.x, where the local REST API was removed. All control goes through `https://scr.daikincloud.net`.

> **Status:** Alpha — confirmed working against a Daikin FTXM12WVJU9 with BRP069C4x adapter (FW 3.1.0). API endpoints confirmed via mitmproxy traffic capture.

---

## Features

- ✅ Email/password authentication via Daikin cloud
- ✅ Automatic token refresh (600s TTL)
- ✅ Climate entity per device: on/off, HVAC mode, target temperature, fan speed
- ✅ Outdoor temperature exposed as extra state attribute
- ✅ Configurable poll interval (default 30s)
- ✅ Config flow UI — no YAML required
- ✅ HACS compatible

---

## Supported Modes

| HA Mode | Daikin `mode=` | Status |
|---|---|---|
| Cool | 3 | ✅ Confirmed |
| Heat | 7 | ⚠️ Inferred |
| Auto | 1 | ⚠️ Inferred |
| Dry | 2 | ⚠️ Inferred |
| Fan Only | 6 | ⚠️ Inferred |

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

The UID is a static hex string embedded in every API request as the `x-daikin-uid` header. Capture it using mitmproxy:

```
x-daikin-uid: dcd2e719644c4716afc1f729e98b609c
```

See [docs/traffic-capture.md](docs/traffic-capture.md) for the full mitmproxy setup guide.

---

## API Notes

See [docs/api_docs.md](docs/api_docs.md) for the full documented API.

**Key confirmed facts from traffic capture:**

| Item | Value |
|---|---|
| Base URL | `https://scr.daikincloud.net` |
| Auth endpoint | `POST /common/login` (form-encoded) |
| Auth header | `authentication: bearer <token>` *(non-standard name)* |
| Control read | `GET /aircon/get_control_info?port=30050&id=<user>` |
| Control write | `GET /aircon/set_control_info?port=30050&...` |
| Response format | Comma-separated `key=value` (not JSON) |
| Token TTL | 600 seconds |

---

## Development

### Project Structure

```
custom_components/daikin_comfort_control/
├── __init__.py        # Entry point, setup/unload
├── manifest.json      # Integration metadata
├── const.py           # Constants, mode/fan mappings
├── daikin_api.py      # Cloud API client (aiohttp)
├── coordinator.py     # DataUpdateCoordinator
├── config_flow.py     # UI config flow
├── climate.py         # Climate platform entity
├── strings.json       # UI strings
└── translations/
    └── en.json        # English translations

docs/
├── api_docs.md        # Confirmed API documentation
└── traffic-capture.md # mitmproxy setup guide
```

### Capture → Implement Workflow

1. Capture traffic with mitmproxy (see [docs/traffic-capture.md](docs/traffic-capture.md))
2. Document new endpoints/params in [docs/api_docs.md](docs/api_docs.md)
3. Update `daikin_api.py` with confirmed values
4. Test via HA Developer Tools → Template or Services before UI testing

---

## Troubleshooting

**"No devices found"** — Check that the device UID matches the `x-daikin-uid` from your capture. Try recapturing the login flow.

**"Cannot connect"** — Verify your HA instance has outbound HTTPS access to `scr.daikincloud.net`.

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

The most valuable contribution right now is **traffic captures** of currently-unconfirmed API behaviors (mode changes, fan speed values, login response body). See [docs/api_docs.md](docs/api_docs.md) for the current unknowns list.
