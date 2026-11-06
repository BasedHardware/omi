import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
// The pinned webview_flutter plugin provides its public testing interface.
// ignore: depend_on_referenced_packages
import 'package:webview_flutter_platform_interface/webview_flutter_platform_interface.dart';

import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/payment_webview_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _WebView extends WebViewPlatform {
  late _Navigation navigation;

  @override
  PlatformWebViewController createPlatformWebViewController(PlatformWebViewControllerCreationParams params) =>
      _Controller(params);

  @override
  PlatformNavigationDelegate createPlatformNavigationDelegate(PlatformNavigationDelegateCreationParams params) =>
      navigation = _Navigation(params);

  @override
  PlatformWebViewWidget createPlatformWebViewWidget(PlatformWebViewWidgetCreationParams params) => _View(params);
}

class _Controller extends PlatformWebViewController {
  _Controller(super.params) : super.implementation();
  @override
  Future<void> setJavaScriptMode(JavaScriptMode mode) async {}
  @override
  Future<void> setPlatformNavigationDelegate(PlatformNavigationDelegate handler) async {}
  @override
  Future<void> loadRequest(LoadRequestParams params) async {}
  @override
  Future<String?> currentUrl() async => 'https://billing.stripe.com/portal';
  @override
  Future<void> reload() async {}
}

class _View extends PlatformWebViewWidget {
  _View(super.params) : super.implementation();
  @override
  Widget build(BuildContext context) => const SizedBox.expand();
}

class _Navigation extends PlatformNavigationDelegate {
  _Navigation(super.params) : super.implementation();
  late PageEventCallback finished;
  late WebResourceErrorCallback failed;
  late HttpResponseErrorCallback httpFailed;
  @override
  Future<void> setOnPageStarted(PageEventCallback callback) async {}
  @override
  Future<void> setOnPageFinished(PageEventCallback callback) async => finished = callback;
  @override
  Future<void> setOnProgress(ProgressCallback callback) async {}
  @override
  Future<void> setOnWebResourceError(WebResourceErrorCallback callback) async => failed = callback;
  @override
  Future<void> setOnHttpError(HttpResponseErrorCallback callback) async => httpFailed = callback;
  @override
  Future<void> setOnNavigationRequest(NavigationRequestCallback callback) async {}
}

void main() {
  late _WebView webView;
  setUp(() {
    Env.overrideApiBaseUrl('http://127.0.0.1:1/');
    PlatformManager.initializeForLocalHarness();
    webView = _WebView();
    WebViewPlatform.instance = webView;
  });
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  Future<void> pump(WidgetTester tester, VoidCallback onLoaded) async {
    final usage = UsageProvider();
    addTearDown(usage.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: PaymentWebViewPage(checkoutUrl: 'https://billing.stripe.com/portal', onLoaded: onLoaded),
      ),
    ));
  }

  testWidgets('portal load is reported once after a real page finishes, never for about:blank', (tester) async {
    var loaded = 0;
    await pump(tester, () => loaded++);
    expect(loaded, 0);
    webView.navigation.finished('about:blank');
    expect(loaded, 0);
    webView.navigation.finished('https://billing.stripe.com/portal');
    webView.navigation.finished('https://billing.stripe.com/portal/payment-methods');
    expect(loaded, 1);
  });

  testWidgets('failed main-frame loads never report portal opened', (tester) async {
    var loaded = 0;
    await pump(tester, () => loaded++);
    webView.navigation.failed(const WebResourceError(errorCode: -1, description: 'offline', isForMainFrame: true));
    webView.navigation.finished('https://billing.stripe.com/portal');
    expect(loaded, 0);
    await tester.pump();
  });

  testWidgets('HTTP failure pages never report portal opened', (tester) async {
    var loaded = 0;
    await pump(tester, () => loaded++);
    webView.navigation.httpFailed(HttpResponseError(
      request: WebResourceRequest(uri: Uri.parse('https://billing.stripe.com/portal')),
    ));
    webView.navigation.finished('https://billing.stripe.com/portal');
    expect(loaded, 0);
  });
}
