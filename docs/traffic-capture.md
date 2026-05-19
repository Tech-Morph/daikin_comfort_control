# Traffic Capture Guide

This guide explains how to capture HTTPS traffic from the Daikin Comfort Control Android app to obtain your `x-daikin-uid` and document the cloud API. It covers the pre-patched APK quickstart, the full DIY APK patching process, Frida SSL bypass injection, and mitmproxy in WireGuard mode.

> **You only need to do this once.** Once you have your `x-daikin-uid`, the HA integration handles everything automatically and the phone setup is no longer needed.

---

## Quick Start — Pre-Patched APK

We already built and tested a patched version of the Daikin Comfort Control APK with the Frida gadget injected. **You do not need to patch anything yourself.** Download it, install it, and skip straight to [Step 4](#step-4--start-mitmproxy-in-wireguard-mode).

> **Download:** [Releases → daikin-comfort-control-frida.apk](https://github.com/Tech-Morph/daikin_comfort_control/releases)

The patched APK is functionally identical to the official app. The only difference is a Frida gadget shared library embedded in the APK that pauses on launch and waits for a script to be injected. Without the Frida script attached, the app behaves exactly like the original.

```bash
# Uninstall the official app if present
adb uninstall com.daikin.daikincomfortcontrol

# Sideload the patched APK
adb install daikin-comfort-control-frida.apk
```

> If you prefer to build the patched APK yourself from the original, follow the **Building the Patched APK** section below. Otherwise skip it entirely.

---

## Prerequisites

### Linux host

```bash
# Python tools
pip install mitmproxy frida-tools

# Android tools (only needed for DIY APK build)
sudo apt install adb apktool zipalign openjdk-17-jdk

# Optional: download APKs without Google account
pip install apkeep
```

### Android device

- **Developer options enabled** — Settings → About Phone → tap Build Number 7×
- **USB debugging enabled**
- **Install unknown APKs enabled** — needed to sideload
- **WireGuard app installed** — [F-Droid](https://f-droid.org/packages/com.wireguard.android/) or Play Store
- Connected to Linux host via USB

---

## Building the Patched APK Yourself (Optional)

Skip this entire section if you're using the pre-patched APK from Releases.

### 1. Get the Official APK

**Option A — Pull from device:**
```bash
adb shell pm list packages | grep daikin
adb shell pm path com.daikin.daikincomfortcontrol
adb pull /data/app/~~<hash>/com.daikin.daikincomfortcontrol-<hash>/base.apk daikin.apk
```

**Option B — apkeep:**
```bash
apkeep -a com.daikin.daikincomfortcontrol -d google-play daikin.apk
```

**Option C** — [APKMirror](https://www.apkmirror.com) or [APKPure](https://apkpure.com)

### 2. Download Frida Gadget

```bash
# Check device arch
adb shell getprop ro.product.cpu.abi
# Common values: arm64-v8a, armeabi-v7a, x86_64

FRIDA_VERSION=$(frida --version)
wget "https://github.com/frida/frida/releases/download/${FRIDA_VERSION}/frida-gadget-${FRIDA_VERSION}-android-arm64.so.xz"
unxz frida-gadget-${FRIDA_VERSION}-android-arm64.so.xz
mv frida-gadget-${FRIDA_VERSION}-android-arm64.so libfrida-gadget.so
```

### 3. Decompile, Inject, Repackage

```bash
apktool d daikin.apk -o daikin_patched/

mkdir -p daikin_patched/lib/arm64-v8a
cp libfrida-gadget.so daikin_patched/lib/arm64-v8a/libfrida-gadget.so
```

Find the main Activity:
```bash
grep -A2 'MAIN' daikin_patched/AndroidManifest.xml
```

In that smali file, add these two lines at the **top of `onCreate`** before any other instruction:
```smali
const-string v0, "frida-gadget"
invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V
```

Repackage and sign:
```bash
apktool b daikin_patched/ -o daikin_frida.apk

# Generate debug keystore (one-time)
keytool -genkey -v -keystore debug.keystore -alias androiddebugkey \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -storepass android -keypass android \
  -dname "CN=Android Debug,O=Android,C=US"

zipalign -v 4 daikin_frida.apk daikin_frida_aligned.apk
apksigner sign \
  --ks debug.keystore --ks-key-alias androiddebugkey \
  --ks-pass pass:android --key-pass pass:android \
  --out daikin_signed.apk daikin_frida_aligned.apk

adb uninstall com.daikin.daikincomfortcontrol
adb install daikin_signed.apk
```

---

## Step 4 — Start mitmproxy in WireGuard Mode

```bash
cd /opt/daikin_integration

mitmweb \
  --mode wireguard \
  --web-port 8083 \
  --web-host 0.0.0.0 \
  --ssl-insecure \
  -s tools/daikin_filter.py
```

mitmweb prints a WireGuard config block in the terminal. Configure it on the phone:

1. Open WireGuard app → tap **+** → **Scan QR code** (or Create from scratch and paste)
2. Enable the tunnel — all phone traffic now routes through mitmproxy
3. Open mitmweb in your browser at `http://<linux-ip>:8083`

> mitmproxy regenerates WireGuard keys on every restart. If you restart mitmweb, re-import the WireGuard config on the phone.

---

## Step 5 — Attach Frida and Inject SSL Bypass

The patched app **freezes on the splash screen** waiting for Frida. This is expected.

```bash
# Forward the Frida gadget port over USB
adb forward tcp:27042 tcp:27042

# Launch the Daikin app on the phone — it will pause on the splash screen

# Attach Frida and inject the bypass
frida -H 127.0.0.1:27042 Gadget -l tools/ssl-bypass.js
```

Expected output in the Frida console:
```
[SSL Bypass] TrustManager + HostnameVerifier installed
[SSL Bypass] OkHttp3 CertificatePinner hooked
[SSL Bypass] All hooks installed - app SSL pinning disabled
```

The app will resume automatically. **Log in with your Daikin Comfort Control credentials.**

---

## Step 6 — Extract Your UID

The `daikin_filter.py` script prints the UID directly to stdout on the first request:

```
================================================================
  POST  https://scr.daikincloud.net/common/login  ->  200
  Time: 2026-05-19T07:15:22Z
  x-daikin-uid   : 51952434f3074927863a37557c01a0bc
  authentication : <redacted>
  REQUEST BODY:
    {
      "grant_type": "password",
      "username": "your@email.com",
      "password": "<redacted>"
    }
================================================================
```

Copy the `x-daikin-uid` value — this is what you enter in the HA integration config flow.

It also appears on every subsequent request (`/common/device_list`, `/aircon/get_control_info`, etc.) so you won't miss it.

All captured traffic is saved to:
- `daikin_api.log` — full timestamped log (tokens included — keep private)
- `daikin_capture.json` — structured JSON array for post-processing

---

## Step 7 — Capture Additional Endpoints (Optional)

While the app is open, interact with controls to capture the full API surface:

| Action | What gets captured |
|---|---|
| Turn on / off | `GET /aircon/set_control_info?...&pow=1` or `pow=0` |
| Change temperature | `...&stemp=22.0&dt3=22.0` |
| Change fan speed | `...&f_rate=3&dfr3=3` |
| Change HVAC mode | `...&mode=3` (1=auto, 2=dry, 3=cool, 4=heat, 6=fan) |
| Poll state | `GET /aircon/get_control_info` |
| Poll sensors | `GET /aircon/get_sensor_info` |
| Token refresh | `POST /common/token_refresh` |

---

## Troubleshooting

**App crashes immediately after patching**
- Wrong smali target — try the `Application` subclass instead of the main `Activity`
- Add `android:extractNativeLibs="true"` to the `<application>` tag in `AndroidManifest.xml`
- Wrong gadget arch — re-check `adb shell getprop ro.product.cpu.abi`

**`frida: unable to connect to remote frida-server`**
- Use capital-G `Gadget` — you're targeting the embedded gadget, not frida-server
- Re-run `adb forward tcp:27042 tcp:27042` after reconnecting USB
- Kill and relaunch the app, reattach Frida before the splash screen times out

**TLS handshake failures in mitmweb for Daikin traffic**
- Bypass didn't attach in time — kill the app, relaunch, reattach Frida first
- Use `--pause` flag: `frida -H 127.0.0.1:27042 Gadget -l tools/ssl-bypass.js --pause` then type `%resume`

**WireGuard active but no traffic in mitmweb**
- Enable IP forwarding: `sudo sysctl -w net.ipv4.ip_forward=1`
- mitmweb was restarted — keys changed, re-scan QR on phone
- Verify mitmweb is listening: `ss -tlnp | grep 8083`

**Certificate errors for non-Daikin apps**
- Expected and harmless — other apps use their own pinning we don't bypass
- Only `scr.daikincloud.net` traffic is needed

---

## Tools Reference

| File | Purpose |
|---|---|
| [`tools/ssl-bypass.js`](../tools/ssl-bypass.js) | Frida script — disables SSL pinning across OkHttp3, TrustManager, Conscrypt, WebView |
| [`tools/daikin_filter.py`](../tools/daikin_filter.py) | mitmproxy addon — filters, logs, and pretty-prints all Daikin API traffic |

---

## Security Notes

- Uninstall the patched APK and reinstall the official app when capture is complete
- **Never commit** `x-daikin-uid`, passwords, or captured tokens to version control
- `daikin_api.log` and `daikin_capture.json` contain live tokens — both are in `.gitignore`
- The UID is tied to the app installation — treat it like a credential
- Run mitmweb only on a trusted local network
