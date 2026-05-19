# Traffic Capture Guide

This guide explains how to capture HTTPS traffic from the Daikin Comfort Control Android app to obtain your `x-daikin-uid` and document the cloud API. It covers SSL certificate pinning bypass using Frida, APK patching, and mitmproxy in WireGuard mode.

> **You only need to do this once.** Once you have your `x-daikin-uid`, the HA integration handles everything automatically.

---

## Prerequisites

### On your Linux machine (host)

```bash
# Python 3.8+ required
pip install mitmproxy frida-tools objection

# Android tools
sudo apt install adb apktool zipalign openjdk-17-jdk

# Optional: apkeep for downloading APKs without a Google account
pip install apkeep
```

### On your Android device

- **Developer options enabled** (Settings → About Phone → tap Build Number 7 times)
- **USB debugging enabled**
- **Install unknown APKs enabled** (needed to sideload the patched APK)
- **WireGuard app installed** ([F-Droid](https://f-droid.org/packages/com.wireguard.android/) or Play Store)
- Connected to your Linux machine via USB

---

## Step 1: Obtain the Daikin Comfort Control APK

You need the original APK before patching. Options:

**Option A — Pull from device if already installed:**
```bash
# Find the package name
adb shell pm list packages | grep daikin

# Get the APK path
adb shell pm path com.daikin.daikincomfortcontrol

# Pull it
adb pull /data/app/~~<hash>/com.daikin.daikincomfortcontrol-<hash>/base.apk daikin.apk
```

**Option B — Download with apkeep:**
```bash
apkeep -a com.daikin.daikincomfortcontrol -d google-play daikin.apk
```

**Option C — Use APKPure or APKMirror** to download `com.daikin.daikincomfortcontrol` manually.

---

## Step 2: Patch the APK with Frida Gadget

Frida gadget is a shared library injected into the APK that lets you run JavaScript hooks at runtime — including disabling SSL certificate pinning.

### 2a. Download the correct Frida gadget

```bash
# Check your device architecture
adb shell getprop ro.product.cpu.abi
# Common values: arm64-v8a, armeabi-v7a, x86_64

# Download matching gadget from https://github.com/frida/frida/releases
# Example for arm64-v8a:
FRIDA_VERSION=$(frida --version)
wget "https://github.com/frida/frida/releases/download/${FRIDA_VERSION}/frida-gadget-${FRIDA_VERSION}-android-arm64.so.xz"
unxz frida-gadget-${FRIDA_VERSION}-android-arm64.so.xz
mv frida-gadget-${FRIDA_VERSION}-android-arm64.so libfrida-gadget.so
```

### 2b. Decompile the APK

```bash
mkdir daikin_patched
apktool d daikin.apk -o daikin_patched/
```

### 2c. Inject the gadget

```bash
# Copy gadget into the correct arch lib folder
mkdir -p daikin_patched/lib/arm64-v8a   # adjust arch as needed
cp libfrida-gadget.so daikin_patched/lib/arm64-v8a/libfrida-gadget.so
```

Now find the app's main Activity smali file. Look in `daikin_patched/smali*` for the main launcher activity:

```bash
# Find the main activity class from AndroidManifest.xml
grep -A2 'MAIN' daikin_patched/AndroidManifest.xml
# Look for android:name="com.daikin.xxx.MainActivity" or similar

# Open that smali file
# Example:
nano daikin_patched/smali/com/daikin/daikincomfortcontrol/MainActivity.smali
```

In the `onCreate` method, add this line **before** the first other instruction to load the gadget:

```smali
const-string v0, "frida-gadget"
invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V
```

Full example of a patched `onCreate`:
```smali
.method protected onCreate(Landroid/os/Bundle;)V
    .locals 1

    # === Frida gadget injection ===
    const-string v0, "frida-gadget"
    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V
    # === end injection ===

    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V
    return-void
.end method
```

### 2d. Repackage and sign

```bash
# Rebuild the APK
apktool b daikin_patched/ -o daikin_frida.apk

# Generate a debug keystore (skip if you already have one)
keytool -genkey -v \
  -keystore debug.keystore \
  -alias androiddebugkey \
  -keyalg RSA -keysize 2048 \
  -validity 10000 \
  -storepass android \
  -keypass android \
  -dname "CN=Android Debug,O=Android,C=US"

# Align
zipalign -v 4 daikin_frida.apk daikin_frida_aligned.apk

# Sign
apksigner sign \
  --ks debug.keystore \
  --ks-key-alias androiddebugkey \
  --ks-pass pass:android \
  --key-pass pass:android \
  --out daikin_signed.apk \
  daikin_frida_aligned.apk
```

### 2e. Install the patched APK

```bash
# Uninstall original first
adb uninstall com.daikin.daikincomfortcontrol

# Install patched version
adb install daikin_signed.apk
```

---

## Step 3: Write the SSL Bypass Script

Save this as `ssl-bypass.js` on your Linux machine:

```javascript
// ssl-bypass.js
// Disables SSL certificate validation and unpins certificates
// in Android apps using OkHttp, TrustManager, and WebView

Java.perform(function () {

  // --- Disable TrustManager certificate validation ---
  var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
  var SSLContext = Java.use('javax.net.ssl.SSLContext');

  var TrustManager = Java.registerClass({
    name: 'com.custom.TrustManager',
    implements: [X509TrustManager],
    methods: {
      checkClientTrusted: function (chain, authType) {},
      checkServerTrusted: function (chain, authType) {},
      getAcceptedIssuers: function () { return []; }
    }
  });

  var TrustManagers = [TrustManager.$new()];
  var sslContext = SSLContext.getInstance('TLS');
  sslContext.init(null, TrustManagers, null);
  var defaultSSLSocketFactory = sslContext.getSocketFactory();

  var HttpsURLConnection = Java.use('javax.net.ssl.HttpsURLConnection');
  HttpsURLConnection.setDefaultSSLSocketFactory(defaultSSLSocketFactory);
  HttpsURLConnection.setDefaultHostnameVerifier(
    Java.registerClass({
      name: 'com.custom.HostnameVerifier',
      implements: [Java.use('javax.net.ssl.HostnameVerifier')],
      methods: {
        verify: function (hostname, session) { return true; }
      }
    }).$new()
  );

  // --- OkHttp3 CertificatePinner bypass ---
  try {
    var CertificatePinner = Java.use('okhttp3.CertificatePinner');
    CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function () {
      console.log('[SSL Bypass] OkHttp3 CertificatePinner.check() bypassed');
    };
    CertificatePinner.check.overload('java.lang.String', 'kotlin.jvm.functions.Function0').implementation = function () {
      console.log('[SSL Bypass] OkHttp3 CertificatePinner.check() (kotlin) bypassed');
    };
  } catch (e) {
    console.log('[SSL Bypass] OkHttp3 CertificatePinner not found: ' + e);
  }

  // --- OkHttp3 TrustRootIndex bypass ---
  try {
    var TrustRootIndex = Java.use('okhttp3.internal.tls.TrustRootIndex');
    TrustRootIndex.get.implementation = function () {
      console.log('[SSL Bypass] OkHttp3 TrustRootIndex.get() bypassed');
      return null;
    };
  } catch (e) {}

  // --- Android Network Security Config bypass ---
  try {
    var NetworkSecurityTrustManager = Java.use(
      'android.security.net.config.NetworkSecurityTrustManager'
    );
    NetworkSecurityTrustManager.checkServerTrusted.implementation = function () {
      console.log('[SSL Bypass] NetworkSecurityTrustManager bypassed');
    };
  } catch (e) {}

  // --- WebViewClient bypass (for WebView-based flows) ---
  try {
    var WebViewClient = Java.use('android.webkit.WebViewClient');
    WebViewClient.onReceivedSslError.implementation = function (view, handler, error) {
      handler.proceed();
    };
  } catch (e) {}

  console.log('[SSL Bypass] All hooks installed successfully');
});
```

---

## Step 4: Start mitmproxy in WireGuard Mode

On your Linux machine:

```bash
cd /opt/daikin_integration
source venv/bin/activate

mitmweb \
  --mode wireguard \
  --web-port 8083 \
  --web-host 0.0.0.0 \
  --ssl-insecure
```

mitmweb will print a WireGuard config block:

```ini
[Interface]
PrivateKey = <generated>
Address = 10.0.0.1/32
DNS = 10.0.0.53

[Peer]
PublicKey = <generated>
AllowedIPs = 0.0.0.0/0
Endpoint = <your-linux-ip>:51820
```

**Configure WireGuard on the phone:**
1. Open the WireGuard app → tap **+** → **Create from QR code** or **Create from scratch**
2. If no QR is shown, paste the config manually
3. Enable the tunnel — all traffic now routes through mitmproxy

> **Note:** mitmproxy regenerates WireGuard keys on every restart. If you restart mitmweb, you must re-import the config on the phone.

Open mitmweb in your browser at `http://<linux-ip>:8083`.

---

## Step 5: Launch the App with Frida

With the patched APK installed and WireGuard active, attach Frida to inject the SSL bypass:

```bash
# Forward the Frida gadget port
adb forward tcp:27042 tcp:27042

# The app pauses on launch waiting for Frida
# Open the Daikin app on the phone — it will freeze on the splash screen

# Attach Frida and inject the bypass script
frida -H 127.0.0.1:27042 Gadget -l /path/to/ssl-bypass.js
```

You should see in the Frida console:
```
[SSL Bypass] OkHttp3 CertificatePinner.check() bypassed
[SSL Bypass] All hooks installed successfully
```

The app will resume. **Log in with your Daikin Comfort Control credentials.**

---

## Step 6: Extract the UID from mitmweb

In the mitmweb browser UI (`http://<linux-ip>:8083`), you will see the login request:

```
POST https://scr.daikincloud.net/common/login
```

Click it and look at the **Request Headers**:

```
x-daikin-uid: 51952434f3074927863a37557c01a0bc
```

That 32-character hex string is your UID. **Copy it** — this is what you enter in the HA integration config flow.

You will also see it on every subsequent request (`GET /common/device_list`, `GET /aircon/get_control_info`, etc.).

---

## Step 7: Verify Additional Endpoints (Optional)

While the app is open, interact with it to capture control commands:

- **Turn the unit on/off** → captures `GET /aircon/set_control_info?...&pow=1...`
- **Change temperature** → captures `stemp=<value>` param
- **Change fan speed** → captures `f_rate=<value>` param
- **Change mode** → captures `mode=<n>` param

All captured traffic is logged to the mitmweb UI and (if you used the filter script) to stdout in JSON format.

---

## Troubleshooting

### App crashes on launch after patching
- Wrong smali method targeted — try the `Application` subclass instead of `Activity`
- Missing `android:extractNativeLibs="true"` in `AndroidManifest.xml` — add it to the `<application>` tag
- Wrong gadget architecture — re-check `adb shell getprop ro.product.cpu.abi`

### Frida says "unable to connect to remote frida-server"
- The gadget is embedded in the APK and listens on the device, not frida-server
- Use `frida -H 127.0.0.1:27042 Gadget` (capital G, "Gadget" not the package name)
- Make sure `adb forward tcp:27042 tcp:27042` ran after connecting USB

### mitmweb shows TLS handshake failures for Daikin traffic
- SSL bypass script didn't attach in time — kill and relaunch the app, re-attach Frida before the app reaches the login screen
- Try `frida -H 127.0.0.1:27042 Gadget -l ssl-bypass.js --pause` then `%resume` in the Frida REPL

### WireGuard tunnel active but no traffic in mitmweb
- IP forwarding not enabled: `sudo sysctl -w net.ipv4.ip_forward=1`
- mitmweb was restarted — keys changed, re-scan QR on phone
- Check mitmweb is actually running: `ps aux | grep mitmweb`

### "certificate unknown" errors for non-Daikin traffic
This is expected and harmless. Apps like Google services, Facebook, and Proton use their own certificate pinning that the Frida script doesn't target. Only `scr.daikincloud.net` traffic needs to be intercepted.

---

## Security Notes

- The patched APK is for **capture purposes only** — uninstall it and reinstall the official app when done
- Never commit your `x-daikin-uid`, password, or captured tokens to version control
- The UID is tied to your app installation; treat it like a password
- mitmweb should only be run on a trusted local network
