/**
 * ssl-bypass.js
 * Frida script to disable SSL certificate pinning in the
 * Daikin Comfort Control Android app (and most OkHttp3-based apps).
 *
 * Usage:
 *   frida -H 127.0.0.1:27042 Gadget -l ssl-bypass.js
 *
 * Targets:
 *   - javax.net.ssl.TrustManager (blanket trust)
 *   - javax.net.ssl.HostnameVerifier (blanket allow)
 *   - okhttp3.CertificatePinner (Java + Kotlin overloads)
 *   - okhttp3.internal.tls.TrustRootIndex
 *   - android.security.net.config.NetworkSecurityTrustManager
 *   - android.webkit.WebViewClient (WebView SSL errors)
 *   - com.android.org.conscrypt.TrustManagerImpl (Conscrypt)
 */

Java.perform(function () {

  // --- Blanket TrustManager ---------------------------------------------------
  var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
  var SSLContext       = Java.use('javax.net.ssl.SSLContext');

  var TrustManager = Java.registerClass({
    name: 'com.custom.TrustManager',
    implements: [X509TrustManager],
    methods: {
      checkClientTrusted: function (chain, authType) {},
      checkServerTrusted: function (chain, authType) {},
      getAcceptedIssuers:  function () { return []; }
    }
  });

  var sslCtx = SSLContext.getInstance('TLS');
  sslCtx.init(null, [TrustManager.$new()], null);
  var factory = sslCtx.getSocketFactory();

  var HttpsURLConnection = Java.use('javax.net.ssl.HttpsURLConnection');
  HttpsURLConnection.setDefaultSSLSocketFactory(factory);
  HttpsURLConnection.setDefaultHostnameVerifier(
    Java.registerClass({
      name: 'com.custom.HostnameVerifier',
      implements: [Java.use('javax.net.ssl.HostnameVerifier')],
      methods: {
        verify: function (hostname, session) { return true; }
      }
    }).$new()
  );
  console.log('[SSL Bypass] TrustManager + HostnameVerifier installed');

  // --- OkHttp3 CertificatePinner ----------------------------------------------
  try {
    var CertPinner = Java.use('okhttp3.CertificatePinner');

    CertPinner.check
      .overload('java.lang.String', 'java.util.List')
      .implementation = function (host, certs) {
        console.log('[SSL Bypass] OkHttp3 CertificatePinner.check(List) bypassed for: ' + host);
      };

    CertPinner.check
      .overload('java.lang.String', 'kotlin.jvm.functions.Function0')
      .implementation = function (host, fn) {
        console.log('[SSL Bypass] OkHttp3 CertificatePinner.check(Function0) bypassed for: ' + host);
      };

    console.log('[SSL Bypass] OkHttp3 CertificatePinner hooked');
  } catch (e) {
    console.log('[SSL Bypass] OkHttp3 CertificatePinner not found: ' + e);
  }

  // --- OkHttp3 TrustRootIndex -------------------------------------------------
  try {
    var TrustRootIndex = Java.use('okhttp3.internal.tls.TrustRootIndex');
    TrustRootIndex.get.implementation = function () {
      console.log('[SSL Bypass] OkHttp3 TrustRootIndex.get() bypassed');
      return null;
    };
  } catch (e) {
    // Not present in all OkHttp versions - safe to ignore
  }

  // --- Android Network Security Config ----------------------------------------
  try {
    var NSConfig = Java.use('android.security.net.config.NetworkSecurityTrustManager');
    NSConfig.checkServerTrusted.implementation = function (chain, authType, host) {
      console.log('[SSL Bypass] NetworkSecurityTrustManager bypassed for: ' + host);
    };
  } catch (e) {
    console.log('[SSL Bypass] NetworkSecurityTrustManager not found: ' + e);
  }

  // --- Conscrypt TrustManagerImpl ---------------------------------------------
  try {
    var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
    TrustManagerImpl.verifyChain.implementation = function (untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
      console.log('[SSL Bypass] Conscrypt TrustManagerImpl.verifyChain() bypassed for: ' + host);
      return untrustedChain;
    };
  } catch (e) {
    // Not always present
  }

  // --- WebViewClient ----------------------------------------------------------
  try {
    var WebViewClient = Java.use('android.webkit.WebViewClient');
    WebViewClient.onReceivedSslError.implementation = function (view, handler, error) {
      handler.proceed();
      console.log('[SSL Bypass] WebViewClient.onReceivedSslError() bypassed');
    };
  } catch (e) {
    console.log('[SSL Bypass] WebViewClient not found: ' + e);
  }

  console.log('[SSL Bypass] All hooks installed - app SSL pinning disabled');
});
