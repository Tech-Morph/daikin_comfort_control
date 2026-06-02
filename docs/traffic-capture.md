# Traffic Capture Guide — Daikin Comfort Control

This guide explains how to capture HTTPS traffic from the Daikin Comfort Control mobile app using mitmproxy. This is needed to obtain your `x-daikin-uid` and verify API behavior.

---

## Requirements

- A PC or VM running mitmproxy
- An Android device (or emulator) with the Daikin Comfort Control app installed
- Both devices on the same Wi-Fi network

---

## Setup

### 1. Install mitmproxy

```bash
pip install mitmproxy
# or download from https://mitmproxy.org
```

### 2. Start mitmproxy web UI

```bash
mitmweb --listen-port 8082
```

This opens the web UI at `http://127.0.0.1:8081`.

### 3. Configure Android proxy

1. On your Android device: **Settings → Wi-Fi → long-press your network → Modify → Advanced**
2. Set proxy to **Manual**
3. Hostname: your PC’s local IP (e.g. `192.168.1.x`)
4. Port: `8082`

### 4. Install mitmproxy CA certificate on Android

1. With proxy configured, open the browser on Android and go to `mitm.it`
2. Download and install the Android certificate
3. Trust it under **Settings → Security → Trusted Credentials → User**

> **Android 7+ note:** Apps targeting API 24+ do not trust user-installed CAs by default. You may need a rooted device, an older Android version, or an Android emulator with a writable system partition to intercept app traffic.

---

## Capturing Traffic

1. Open the Daikin Comfort Control app
2. Navigate to your device and interact (change mode, temperature, fan speed)
3. Switch to mitmproxy web UI and look for requests to `scr.daikincloud.net`

### Key values to capture

| Value | Where to find it |
|---|---|
| `x-daikin-uid` | Any request header to `scr.daikincloud.net` |
| `access_token` | Response body of `POST /common/login` |
| `refresh_token` | Response body of `POST /common/login` |

**The `x-daikin-uid` is the only value you need to copy.** It is a static hex string tied to your adapter hardware and does not change. Example format: `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` (32 hex chars).

---

## Example Flow

After app login you will see a `POST /common/login` request. Click it in mitmproxy → **Request** tab to see the form body, **Response** tab to see the tokens.

All subsequent requests to `scr.daikincloud.net` will include:

```
authentication: bearer <access_token>
x-daikin-uid: <your_uid>
```

---

## Export Flows

To save all captured flows for later analysis:

```bash
# In mitmweb: File → Save
# Or from CLI:
mitmproxy -r flows.bin
```

---

## Security Notes

- **Do not share your `access_token` or `refresh_token`** — they grant full control of your AC unit
- **Do not share your `x-daikin-uid`** — it is tied to your hardware
- **Do not commit credentials to version control** — use HA’s config entry storage instead
- Tokens expire after 10 minutes; the integration handles refresh automatically
- The `x-daikin-uid` is the only value that needs to be entered into the integration config flow
