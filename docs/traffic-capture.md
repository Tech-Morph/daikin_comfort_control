# Traffic Capture Guide

> How to intercept Daikin Comfort Control app traffic using mitmproxy to document the cloud API.

---

## Setup

### Requirements

- PC running mitmproxy (v12.x confirmed working)
- Android device or emulator with Daikin Comfort Control app installed
- Both devices on the same LAN segment

### mitmproxy Setup

```bash
# Install
pip install mitmproxy

# Run the web UI (recommended for capture review)
mitmweb --listen-port 8082
```

Browse to `http://192.168.x.x:8082` from your browser.

### Android Proxy Configuration

1. On Android: **Settings → Wi-Fi → Long-press network → Modify → Advanced → Proxy → Manual**
2. Set proxy host to your PC's LAN IP, port `8082`
3. Install mitmproxy CA cert:
   - Browse to `http://mitm.it` on the Android device
   - Download and install the Android cert
   - On Android 7+: **Settings → Security → Install from storage**

### Android 7+ Certificate Trust (Required)

Android 7+ restricts user-installed CA certs to system trust. The app must trust user CAs or you must root/use an emulator with a system-level cert injection.

**Option A (Emulator — easiest):**
```bash
# Start emulator with writable system partition
emulator -avd <name> -writable-system
adb root
adb remount
adb push ~/.mitmproxy/mitmproxy-ca-cert.cer /system/etc/security/cacerts/<hash>.0
adb reboot
```

**Option B (Network Security Config — app mod):**
Decompile the APK with `apktool`, add a `network_security_config.xml` that trusts user CAs, recompile and sign.

---

## Confirmed Captures (2026-06-02)

### Auth Flow

```
POST https://scr.daikincloud.net/common/login

Headers:
  x-daikin-uid: dcd2e719644c4716afc1f729e98b609c
  user-agent: okhttp/4.9.2
  content-type: application/x-www-form-urlencoded
  accept-encoding: gzip

Body (URL-encoded):
  grant_type=password
  scope=smart_app
  username=TechMorph
  password=<redacted>
```

### Device List

```
GET https://scr.daikincloud.net/common/device_list

Headers:
  authentication: bearer <token>
  x-daikin-uid: dcd2e719644c4716afc1f729e98b609c
  user-agent: okhttp/4.9.2
  accept-encoding: gzip
```

### Get Control Info

```
GET https://scr.daikincloud.net/aircon/get_control_info
    ?port=30050&port=30050&apw=&id=TechMorph&spw=

Headers:
  authentication: bearer <token>
  x-daikin-uid: dcd2e719644c4716afc1f729e98b609c
  user-agent: okhttp/4.9.2
  accept-encoding: gzip
```

### Set Control Info (Temperature Change to 20.5°C)

```
GET https://scr.daikincloud.net/aircon/set_control_info
    ?port=30050&mode=3&dt3=20.5&f_dir_ud=0&f_rate=A
    &shum=0&f_dir_lr=0&pow=1&stemp=20.5&dh3=0

Headers:
  authentication: bearer <token>
  x-daikin-uid: dcd2e719644c4716afc1f729e98b609c
  user-agent: okhttp/4.9.2
  accept-encoding: gzip
```

### Set Control Info (Temperature Change to 20.0°C)

```
GET https://scr.daikincloud.net/aircon/set_control_info
    ?port=30050&mode=3&dt3=20.0&f_dir_ud=0&f_rate=A
    &shum=0&f_dir_lr=0&pow=1&stemp=20.0&dh3=0

Headers:
  authentication: bearer <token>
  x-daikin-uid: dcd2e719644c4716afc1f729e98b609c
  user-agent: okhttp/4.9.2
  accept-encoding: gzip
```

---

## Key Findings

| Finding | Detail |
|---|---|
| Real base URL | `https://scr.daikincloud.net` (not `api.daikinskyport.com`) |
| Auth header name | `authentication` (non-standard — not `Authorization`) |
| Token format | Long hex bearer token (~190 chars) |
| Token TTL | `expires_in: "600"` (string, 10 minutes) |
| Control method | `GET` (not `PUT`/`POST`) for set_control_info |
| Response format | Comma-separated `key=value` pairs (not JSON) |
| Port param | `port=30050` — static routing identifier in cloud proxy |
| UID | Static per-adapter hex string in `x-daikin-uid` header |

---

## What to Capture Next

To fill in remaining unknowns, trigger each of these in the app while mitmproxy is running, then click the **Response** tab for each captured flow:

1. **Login response** — click the `POST /common/login` flow → Response tab
   - Confirm field names (`access_token`, `refresh_token`, `expires_in`)
   - Note exact `expires_in` type (string vs int)

2. **device_list response** — click `GET /common/device_list` → Response tab
   - Capture the full response body to confirm device field structure

3. **Mode change to Heat** — set app to Heat mode
   - Confirm `mode=7` (or whatever value appears)

4. **Mode change to Auto** — set app to Auto mode
   - Confirm `mode=1`

5. **Fan speed change** — tap each fan speed in the app
   - Confirm `f_rate` values for Low / Medium / High

6. **Power off** — turn unit off in app
   - Confirm `pow=0` in set_control_info

7. **set_control_info response** — check any set flow → Response tab
   - Confirm `ret=OK` format

---

## mitmproxy Export Tips

```python
# Save all flows to a file for offline analysis
# In mitmweb: Flow List → select all → Download

# Or from mitmproxy CLI:
mitmproxy -r flows.bin  # replay/inspect saved flows
```

Filter to only Daikin traffic in mitmweb:
```
Filter: ~d daikincloud.net
```
