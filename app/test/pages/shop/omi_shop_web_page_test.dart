// The hardware-only store's web view wiring, on a fake web view: the device page stays behind the
// loading state until the app-hardware marker check passes, and every failed check or blocked
// navigation shows "This page isn't available in the app." instead of the page.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
// The pinned webview_flutter plugin provides its public testing interface.
// ignore: depend_on_referenced_packages
import 'package:webview_flutter_platform_interface/webview_flutter_platform_interface.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/widgets/omi_web_page.dart';
import 'package:omi/pages/shop/omi_shop.dart';
import 'package:omi/ui/ui.dart';

const _notAvailable = "This page isn't available in the app.";
const _product = 'https://www.omi.me/products/omi?view=app-hardware&_ref=test';

class _WebView extends WebViewPlatform {
  late _Controller controller;
  late _Navigation navigation;

  @override
  PlatformWebViewController createPlatformWebViewController(PlatformWebViewControllerCreationParams params) =>
      controller = _Controller(params);

  @override
  PlatformNavigationDelegate createPlatformNavigationDelegate(PlatformNavigationDelegateCreationParams params) =>
      navigation = _Navigation(params);

  @override
  PlatformWebViewWidget createPlatformWebViewWidget(PlatformWebViewWidgetCreationParams params) => _View(params);
}

class _Controller extends PlatformWebViewController {
  _Controller(super.params) : super.implementation();

  final loaded = <Uri>[];
  final scripts = <String>[];
  Completer<Object> marker = Completer<Object>();

  @override
  Future<void> setJavaScriptMode(JavaScriptMode mode) async {}
  @override
  Future<void> setPlatformNavigationDelegate(PlatformNavigationDelegate handler) async {}
  @override
  Future<void> loadRequest(LoadRequestParams params) async => loaded.add(params.uri);
  @override
  Future<Object> runJavaScriptReturningResult(String javaScript) {
    scripts.add(javaScript);
    return marker.future;
  }

  @override
  Future<bool> canGoBack() async => false;
}

class _View extends PlatformWebViewWidget {
  _View(super.params) : super.implementation();
  @override
  Widget build(BuildContext context) => const SizedBox.expand(key: Key('web_content'));
}

class _Navigation extends PlatformNavigationDelegate {
  _Navigation(super.params) : super.implementation();
  late NavigationRequestCallback request;
  late PageEventCallback started;
  late PageEventCallback finished;
  @override
  Future<void> setOnNavigationRequest(NavigationRequestCallback callback) async => request = callback;
  @override
  Future<void> setOnPageStarted(PageEventCallback callback) async => started = callback;
  @override
  Future<void> setOnPageFinished(PageEventCallback callback) async => finished = callback;
  @override
  Future<void> setOnUrlChange(UrlChangeCallback callback) async {}
  @override
  Future<void> setOnWebResourceError(WebResourceErrorCallback callback) async {}
}

void main() {
  late _WebView webView;
  setUp(() {
    webView = _WebView();
    WebViewPlatform.instance = webView;
  });

  Future<void> openStore(WidgetTester tester) async {
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Builder(
        builder: (context) => TextButton(
          onPressed: () => Navigator.of(context).push(MaterialPageRoute<WebNavigationKind>(
            builder: (_) => OmiWebPage(
              title: 'Get Omi',
              url: Uri.parse(_product),
              showClose: true,
              navigationPolicy: omiHardwareNavigation,
              pageCheck: omiHardwarePageCheck,
            ),
          )),
          child: const Text('open'),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1)); // route transition (the spinner never settles)
    webView.navigation.started(_product);
    webView.navigation.finished(_product);
    await tester.pump();
  }

  bool covered(WidgetTester tester) => find.byType(OmiLoadingState).evaluate().isNotEmpty;

  Future<void> expectBlockedWithClose(WidgetTester tester) async {
    expect(find.byKey(const Key('omi_web_page_unavailable')), findsOneWidget);
    expect(find.text(_notAvailable), findsOneWidget);
    final close = find.descendant(of: find.byKey(const Key('omi_web_page_unavailable')), matching: find.text('Close'));
    expect(close, findsOneWidget);
    await tester.tap(close);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(OmiWebPage), findsNothing);
  }

  testWidgets('the device page stays covered by the loading state until the marker check passes', (tester) async {
    await openStore(tester);
    expect(webView.controller.loaded, [Uri.parse(_product)]);
    expect(webView.controller.scripts, [omiHardwareMarkerScript]);
    expect(covered(tester), isTrue);
    await tester.pump(const Duration(seconds: 2));
    expect(covered(tester), isTrue);
    webView.controller.marker.complete(true);
    await tester.pump();
    await tester.pump();
    expect(covered(tester), isFalse);
    expect(find.text(_notAvailable), findsNothing);
  });

  testWidgets('a missing marker shows "not available" with Close and never the page', (tester) async {
    await openStore(tester);
    webView.controller.marker.complete(false);
    await tester.pump();
    expect(covered(tester), isFalse);
    await expectBlockedWithClose(tester);
  });

  testWidgets('a marker script that throws shows the same blocked state', (tester) async {
    await openStore(tester);
    webView.controller.marker.completeError(Exception('script failed'));
    await tester.pump();
    await expectBlockedWithClose(tester);
  });

  testWidgets('a marker script that never answers times out into the blocked state', (tester) async {
    await openStore(tester);
    await tester.pump(omiHardwarePageCheck.timeout - const Duration(milliseconds: 100));
    expect(covered(tester), isTrue);
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump();
    await expectBlockedWithClose(tester);
  });

  testWidgets('a blocked navigation stays on the page and says it is not available', (tester) async {
    await openStore(tester);
    webView.controller.marker.complete(true);
    await tester.pump();
    for (final url in ['https://app.omi.me/', 'https://www.omi.me/products/omi-pro-first-3-months']) {
      final decision = await webView.navigation.request(NavigationRequest(url: url, isMainFrame: true));
      expect(decision, NavigationDecision.prevent, reason: url);
      await tester.pump();
      expect(find.text(_notAvailable), findsOneWidget, reason: url);
      await tester.pump(const Duration(seconds: 10));
      await tester.pump(const Duration(seconds: 1));
    }
    expect(find.byType(OmiWebPage), findsOneWidget);
  });
}
