import 'package:omi/pages/paywall/web_paywall_page.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import '../support/recording_analytics.dart';
// Verifies native Checkout refreshes backend-owned subscription and allowance state.
// Redirect success never grants an entitlement locally; cancellation preserves state.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
// The pinned webview_flutter plugin provides its public testing interface.
// ignore: depend_on_referenced_packages
import 'package:webview_flutter_platform_interface/webview_flutter_platform_interface.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/pages/settings/payment_webview_page.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/utils/platform/platform_manager.dart';

const _freeAllowance = TranscriptionAllowanceSnapshot(mode: 'on_device', reason: 'free_plan', remainingSeconds: 600);
const _paidAllowance = TranscriptionAllowanceSnapshot(mode: 'managed', reason: 'paid_plan');

UserSubscriptionResponse _subscription(PlanType plan, TranscriptionAllowanceSnapshot allowance) {
  return UserSubscriptionResponse(
    subscription: Subscription(
      plan: plan,
      status: SubscriptionStatus.active,
      stripeSubscriptionId: plan.isPaid ? 'sub_paid' : null,
      currentPriceId: plan.isPaid ? 'price_unlimited_v2_year' : null,
    ),
    transcriptionSecondsUsed: 0,
    transcriptionSecondsLimit: 0,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
    transcriptionAllowance: allowance,
  );
}

class _Usage extends UsageProvider {
  _Usage({required Future<UserSubscriptionResponse?> Function() subscriptionRequest})
      : super(subscriptionRequest: subscriptionRequest);

  @override
  Future<void> loadAvailablePlans() async {}

  @override
  Future<Map<String, dynamic>?> createUserCheckoutSession({
    required String priceId,
    String? promotionCode,
    int? trialDays,
  }) async {
    return {'url': 'https://checkout.stripe.com/session'};
  }
}

class _Harness extends StatefulWidget {
  const _Harness();

  @override
  State<_Harness> createState() => _HarnessState();
}

class _HarnessState extends State<_Harness> with TickerProviderStateMixin {
  late final AnimationController _animation = AnimationController(vsync: this);

  @override
  void dispose() {
    _animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PlansSheet(
      waveController: _animation,
      notesController: _animation,
      arrowController: _animation,
      arrowAnimation: _animation,
      readStorefrontGate: () async => false,
    );
  }
}

class _WebView extends WebViewPlatform {
  late _Navigation navigation;
  late _Controller controller;

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
  JavaScriptChannelParams? channel;
  @override
  Future<void> setBackgroundColor(Color color) async {}
  @override
  Future<void> addJavaScriptChannel(JavaScriptChannelParams params) async {
    channel = params;
  }

  _Controller(super.params) : super.implementation();

  @override
  Future<void> setJavaScriptMode(JavaScriptMode mode) async {}

  @override
  Future<void> setPlatformNavigationDelegate(PlatformNavigationDelegate handler) async {}

  @override
  Future<void> loadRequest(LoadRequestParams params) async {}
}

class _View extends PlatformWebViewWidget {
  _View(super.params) : super.implementation();

  @override
  Widget build(BuildContext context) => const SizedBox.expand();
}

class _Navigation extends PlatformNavigationDelegate {
  _Navigation(super.params) : super.implementation();

  late NavigationRequestCallback navigate;
  late WebResourceErrorCallback resourceError;

  @override
  Future<void> setOnPageStarted(PageEventCallback callback) async {}

  @override
  Future<void> setOnPageFinished(PageEventCallback callback) async {}

  @override
  Future<void> setOnProgress(ProgressCallback callback) async {}

  @override
  Future<void> setOnWebResourceError(WebResourceErrorCallback callback) async {
    resourceError = callback;
  }

  @override
  Future<void> setOnHttpError(void Function(HttpResponseError error) callback) async {}

  @override
  Future<void> setOnNavigationRequest(NavigationRequestCallback callback) async => navigate = callback;
}

Future<_Usage> _pumpSheet(
  WidgetTester tester, {
  required _WebView webView,
  required UserSubscriptionResponse refreshedSubscription,
  required void Function() onSubscriptionRequest,
}) async {
  tester.view.physicalSize = const Size(430, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  WebViewPlatform.instance = webView;

  final usage = _Usage(
    subscriptionRequest: () async {
      onSubscriptionRequest();
      return refreshedSubscription;
    },
  );
  addTearDown(usage.dispose);
  usage.debugSetSubscription(_subscription(PlanType.basic, _freeAllowance));
  usage.debugSetAvailablePlans({
    'plans': [
      {
        'id': 'price_unlimited_v2_year',
        'plan_id': 'unlimited_v2',
        'title': 'Unlimited Annual',
        'interval': 'year',
        'unit_amount': 26991,
        'price_string': r'$269.91/yr',
        'is_active': false,
      },
      {
        'id': 'price_unlimited_v2_month',
        'plan_id': 'unlimited_v2',
        'title': 'Unlimited Monthly',
        'interval': 'month',
        'unit_amount': 2999,
        'price_string': r'$29.99/mo',
        'is_active': false,
      },
    ],
  });

  await tester.pumpWidget(
    ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: [Locale('en')],
        home: Scaffold(body: _Harness()),
      ),
    ),
  );
  await tester.pump();
  await tester.ensureVisible(find.byKey(const ValueKey('plans_sheet_upgrade_button')));
  await tester.tap(find.byKey(const ValueKey('plans_sheet_upgrade_button')));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  expect(find.byType(PaymentWebViewPage), findsOneWidget);
  return usage;
}

void main() {
  late RecordingAnalytics telemetry;
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TranscriptionAllowanceCache.clear();
    Env.overrideApiBaseUrl('http://127.0.0.1:1/');
    PlatformManager.initializeForLocalHarness();
    AnalyticsManager.resetForTesting();
    telemetry = RecordingAnalytics();
    AnalyticsManager.configure(telemetry.adapter);
    await AnalyticsManager.init();
  });

  tearDown(() {
    AnalyticsManager.resetForTesting();
    TranscriptionAllowanceCache.clear();
    Env.clearApiBaseUrlOverrideForTesting();
  });

  testWidgets('successful checkout refreshes the authoritative subscription and allowance cache', (tester) async {
    final webView = _WebView();
    var subscriptionRequests = 0;
    final usage = await _pumpSheet(
      tester,
      webView: webView,
      refreshedSubscription: _subscription(PlanType.unlimitedV2, _paidAllowance),
      onSubscriptionRequest: () => subscriptionRequests++,
    );

    await AnalyticsManager.flushPending(force: true);
    expect(telemetry.propertiesOf('Subscription Paywall Viewed'), hasLength(1));
    expect(telemetry.propertiesOf('Subscription Upgrade Tapped'), hasLength(1));
    expect(telemetry.propertiesOf('Subscription Checkout Opened'), hasLength(1));
    expect(telemetry.propertiesOf('Subscription Checkout Completed'), isEmpty);
    webView.navigation.navigate(NavigationRequest(url: '${Env.apiBaseUrl}v1/payments/success', isMainFrame: true));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    await AnalyticsManager.flushPending(force: true);
    expect(telemetry.propertiesOf('Subscription Checkout Completed'), hasLength(1));
    expect(subscriptionRequests, 1);
    expect(usage.subscription?.subscription.plan, PlanType.unlimitedV2);
    expect(TranscriptionAllowanceCache.current?.mode, TranscriptionAllowanceSnapshot.modeManaged);
    expect(find.byType(PlansSheet), findsOneWidget);
  });

  testWidgets('cancelled checkout neither reports success nor refreshes subscription state', (tester) async {
    final webView = _WebView();
    var subscriptionRequests = 0;
    final usage = await _pumpSheet(
      tester,
      webView: webView,
      refreshedSubscription: _subscription(PlanType.unlimitedV2, _paidAllowance),
      onSubscriptionRequest: () => subscriptionRequests++,
    );
    final l10n = AppLocalizations.of(tester.element(find.byType(PaymentWebViewPage)));

    webView.navigation.navigate(NavigationRequest(url: '${Env.apiBaseUrl}v1/payments/cancel', isMainFrame: true));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    await AnalyticsManager.flushPending(force: true);
    expect(telemetry.propertiesOf('Subscription Checkout Opened'), hasLength(1));
    expect(telemetry.propertiesOf('Subscription Checkout Completed'), isEmpty);
    expect(subscriptionRequests, 0);
    expect(usage.subscription?.subscription.plan, PlanType.basic);
    expect(TranscriptionAllowanceCache.current?.mode, TranscriptionAllowanceSnapshot.modeOnDevice);
    expect(find.text(l10n.subscriptionSuccessfulCharged), findsNothing);
  });
  testWidgets('failed checkout page never completes, including a late success callback', (tester) async {
    final webView = _WebView();
    await _pumpSheet(tester,
        webView: webView,
        refreshedSubscription: _subscription(PlanType.unlimitedV2, _paidAllowance),
        onSubscriptionRequest: () {});
    webView.navigation
        .resourceError(WebResourceError(errorCode: -2, description: 'fixture failure', isForMainFrame: true));
    await tester.pump();
    webView.navigation.navigate(NavigationRequest(url: '${Env.apiBaseUrl}v1/payments/success', isMainFrame: true));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await AnalyticsManager.flushPending(force: true);
    expect(telemetry.propertiesOf('Subscription Checkout Opened'), hasLength(1));
    expect(telemetry.propertiesOf('Subscription Checkout Completed'), isEmpty);
  });
  for (final item in <String, String>{
    'prefix': 'http://127.0.0.1:1/v1/payments/success-extra',
    'extra path': 'http://127.0.0.1:1/v1/payments/success/extra',
    'trailing slash': 'http://127.0.0.1:1/v1/payments/success/',
    'host': 'http://other.invalid:1/v1/payments/success',
    'host suffix': 'http://127.0.0.1.evil.invalid:1/v1/payments/success',
    'scheme': 'https://127.0.0.1:1/v1/payments/success',
    'port': 'http://127.0.0.1:2/v1/payments/success',
    'userinfo': 'http://user@127.0.0.1:1/v1/payments/success',
    'empty userinfo': 'http://@127.0.0.1:1/v1/payments/success',
  }.entries) {
    testWidgets('new completion rejects ${item.key} while preserving the legacy delegate decision', (tester) async {
      final webView = _WebView();
      await _pumpSheet(tester,
          webView: webView,
          refreshedSubscription: _subscription(PlanType.unlimitedV2, _paidAllowance),
          onSubscriptionRequest: () {});
      final decision = await webView.navigation.navigate(NavigationRequest(url: item.value, isMainFrame: true));
      expect(
          decision,
          item.value.startsWith('${Env.apiBaseUrl}v1/payments/success')
              ? NavigationDecision.prevent
              : NavigationDecision.navigate);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      await AnalyticsManager.flushPending(force: true);
      expect(telemetry.propertiesOf('Subscription Checkout Completed'), isEmpty);
      await tester.pumpWidget(const SizedBox());
    });
  }
  testWidgets('exact trusted success permits its session query, deduplicates and suppresses late callbacks',
      (tester) async {
    final webView = _WebView();
    await _pumpSheet(tester,
        webView: webView,
        refreshedSubscription: _subscription(PlanType.unlimitedV2, _paidAllowance),
        onSubscriptionRequest: () {});
    webView.navigation
        .navigate(NavigationRequest(url: '${Env.apiBaseUrl}v1/payments/success?session_id=fixture', isMainFrame: true));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    webView.navigation.navigate(NavigationRequest(url: '${Env.apiBaseUrl}v1/payments/success', isMainFrame: true));
    await AnalyticsManager.flushPending(force: true);
    expect(telemetry.propertiesOf('Subscription Checkout Completed'), hasLength(1));
  });
  testWidgets('dismissal suppresses a late trusted success', (tester) async {
    final webView = _WebView();
    await _pumpSheet(tester,
        webView: webView,
        refreshedSubscription: _subscription(PlanType.unlimitedV2, _paidAllowance),
        onSubscriptionRequest: () {});
    final navigator = Navigator.of(tester.element(find.byType(PaymentWebViewPage)));
    navigator.pop(false);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    webView.navigation.navigate(NavigationRequest(url: '${Env.apiBaseUrl}v1/payments/success', isMainFrame: true));
    await AnalyticsManager.flushPending(force: true);
    expect(telemetry.propertiesOf('Subscription Checkout Completed'), isEmpty);
  });
  testWidgets('embedded web paywall views only ready content and not repeated ready messages', (tester) async {
    final platform = _WebView();
    WebViewPlatform.instance = platform;
    final usage = _Usage(subscriptionRequest: () async => _subscription(PlanType.basic, _freeAllowance));
    addTearDown(usage.dispose);
    usage.debugSetSubscription(_subscription(PlanType.basic, _freeAllowance));
    usage.debugSetAvailablePlans({'plans': <Map<String, Object>>[]});
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: WebPaywallPage(source: 'usage_page', url: Uri.parse('https://fixture.invalid/paywall')))));
    await tester.pump();
    await AnalyticsManager.flushPending(force: true);
    expect(telemetry.propertiesOf('Subscription Paywall Viewed'), isEmpty);
    platform.controller.channel!.onMessageReceived(JavaScriptMessage(message: '{"type":"ready"}'));
    await tester.pump();
    await AnalyticsManager.flushPending(force: true);
    platform.controller.channel!.onMessageReceived(JavaScriptMessage(message: '{"type":"ready"}'));
    await tester.pump();
    await AnalyticsManager.flushPending(force: true);
    expect(telemetry.propertiesOf('Subscription Paywall Viewed'), hasLength(1));
    expect(telemetry.propertiesOf('Subscription Paywall Viewed').single['surface'], 'web_paywall');
    await tester.pumpWidget(const SizedBox());
  });
}
