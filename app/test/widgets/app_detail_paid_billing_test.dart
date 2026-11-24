// A paid Marketplace app on Android waits for the billing provider before it offers or refuses
// Subscribe: loading while the first subscription read is in flight, then Subscribe for a Stripe
// reader or "Not available on Android" for a Google Play-billed reader. Never the disabled label
// for a reader whose provider is not known yet.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/billing/play_billing.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import '../support/fake_play_billing.dart';
import '../support/test_browser.dart';

class _FakeAppProvider extends AppProvider {
  _FakeAppProvider(this.detail);

  final App detail;
  Future<App?> Function()? load;

  @override
  Future<App?> getAppDetails(String id) async => load == null ? detail : await load!();
}

App _app({
  bool enabled = false,
  bool external = false,
  bool paid = false,
  String? paymentLink,
  List<AuthStep> authSteps = const [],
  String? setupCompletedUrl,
}) {
  return App(
    id: 'app-1',
    name: 'Notes Sync',
    author: 'Omi',
    description: 'Syncs notes',
    image: '',
    capabilities: {'chat', if (external) 'external_integration'},
    status: 'approved',
    category: 'productivity',
    approved: true,
    ratingCount: 0,
    enabled: enabled,
    deleted: false,
    isPaid: paid,
    isUserPaid: false,
    paymentLink: paymentLink,
    externalIntegration:
        external ? ExternalIntegration(authSteps: authSteps, setupCompletedUrl: setupCompletedUrl) : null,
  );
}

final class _EnvFields implements EnvFields {
  const _EnvFields();

  @override
  String? get apiBaseUrl => 'http://127.0.0.1:9/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}

UserSubscriptionResponse _response({PlayBillingConfig? play}) => UserSubscriptionResponse(
      subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      playBilling: play,
    );

void main() {
  late TestBrowser browser;
  setUpAll(() {
    Env.init(const _EnvFields());
    PlatformManager.initializeForLocalHarness();
  });

  setUp(() async {
    browser = TestBrowser();
    browser.install();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TranscriptionAllowanceCache.clear();
  });

  tearDown(() => browser.dispose());

  Future<Completer<UserSubscriptionResponse?>> pumpPaidApp(WidgetTester tester) async {
    final gate = Completer<UserSubscriptionResponse?>();
    final platform = FakePlayPlatform();
    final billing = PlayBilling(platform: () => platform, verify: FakePlayServer().call, store: MemoryTokenStore());
    addTearDown(billing.dispose);
    final usage = UsageProvider(subscriptionRequest: () => gate.future, playBilling: billing);
    addTearDown(usage.dispose);
    final app = _app(paid: true, paymentLink: 'https://pay.example.com/app');
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<AppProvider>.value(value: _FakeAppProvider(app)),
          ChangeNotifierProvider<AddAppProvider>.value(value: AddAppProvider()),
          ChangeNotifierProvider<MessageProvider>.value(value: MessageProvider()),
          ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: AppDetailPage(
            app: app,
            preventAutoOpenHomePage: true,
            enableApp: (_) async => (false, ''),
            appDetailsLoader: (_) async => null,
          ),
        ),
      ),
    );
    await tester.pump();
    unawaited(usage.fetchSubscription());
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    return gate;
  }

  Future<void> settle(WidgetTester tester) async {
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
  }

  testWidgets('a Stripe reader waits on loading, then gets Subscribe, never "Not available"', (tester) async {
    final gate = await pumpPaidApp(tester);
    expect(find.byKey(const Key('app_detail_paid_pending')), findsOneWidget);
    expect(find.byKey(const Key('app_detail_paid_unavailable')), findsNothing);
    expect(find.text('Not available on Android'), findsNothing);
    gate.complete(_response());
    await settle(tester);
    expect(find.byKey(const Key('app_detail_paid_pending')), findsNothing);
    expect(find.byKey(const Key('app_detail_paid_unavailable')), findsNothing);
    expect(find.text('Subscribe'), findsWidgets);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('a Google Play-billed reader waits on loading, then sees "Not available on Android"', (tester) async {
    final gate = await pumpPaidApp(tester);
    expect(find.byKey(const Key('app_detail_paid_pending')), findsOneWidget);
    gate.complete(_response(play: playConfig));
    await settle(tester);
    expect(find.byKey(const Key('app_detail_paid_pending')), findsNothing);
    expect(find.byKey(const Key('app_detail_paid_unavailable')), findsOneWidget);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('a failed subscription read ends on "Not available", never a spinner or the payment link',
      (tester) async {
    final gate = await pumpPaidApp(tester);
    expect(find.byKey(const Key('app_detail_paid_pending')), findsOneWidget);
    gate.complete(null);
    await settle(tester);
    expect(find.byKey(const Key('app_detail_paid_pending')), findsNothing);
    expect(find.byKey(const Key('app_detail_paid_unavailable')), findsOneWidget);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('iOS never waits on the billing provider', (tester) async {
    await pumpPaidApp(tester);
    expect(find.byKey(const Key('app_detail_paid_pending')), findsNothing);
    expect(find.byKey(const Key('app_detail_paid_unavailable')), findsNothing);
    expect(find.text('Subscribe'), findsWidgets);
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  /// Opens the paid app page after the first subscription read already failed and a usage read then
  /// cleared the provider's shared error. [answers] are the subscription reads after the first.
  Future<List<int>> openAfterFailedRead(WidgetTester tester, List<UserSubscriptionResponse?> answers) async {
    final reads = <int>[0];
    final platform = FakePlayPlatform();
    final billing = PlayBilling(platform: () => platform, verify: FakePlayServer().call, store: MemoryTokenStore());
    addTearDown(billing.dispose);
    final usage = UsageProvider(
      subscriptionRequest: () async => reads[0]++ == 0 ? null : answers.removeAt(0),
      usageRequest: ({required period, required timeZone}) async => UserUsageResponse(history: []),
      deviceTimeZone: () async => 'UTC',
      playBilling: billing,
    );
    addTearDown(usage.dispose);
    await usage.fetchSubscription();
    await usage.fetchUsageStats(period: 'monthly');
    expect(usage.error, isNull);
    expect(usage.billingProviderFailed, isTrue);
    final app = _app(paid: true, paymentLink: 'https://pay.example.com/app');
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<AppProvider>.value(value: _FakeAppProvider(app)),
          ChangeNotifierProvider<AddAppProvider>.value(value: AddAppProvider()),
          ChangeNotifierProvider<MessageProvider>.value(value: MessageProvider()),
          ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: AppDetailPage(
            app: app,
            preventAutoOpenHomePage: true,
            enableApp: (_) async => (false, ''),
            appDetailsLoader: (_) async => null,
          ),
        ),
      ),
    );
    await settle(tester);
    // Rebuilds never start another read.
    for (var i = 0; i < 5; i++) {
      usage.notifyListeners();
      await tester.pump(const Duration(milliseconds: 100));
    }
    return reads;
  }

  testWidgets('opening the page after a failed read retries once and a Stripe reader gets Subscribe', (tester) async {
    final reads = await openAfterFailedRead(tester, [_response()]);
    expect(reads.single, 2);
    expect(find.byKey(const Key('app_detail_paid_pending')), findsNothing);
    expect(find.byKey(const Key('app_detail_paid_unavailable')), findsNothing);
    expect(find.text('Subscribe'), findsWidgets);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('a retry that fails again ends on "Not available", not a spinner', (tester) async {
    final reads = await openAfterFailedRead(tester, [null]);
    expect(reads.single, 2);
    expect(find.byKey(const Key('app_detail_paid_pending')), findsNothing);
    expect(find.byKey(const Key('app_detail_paid_unavailable')), findsOneWidget);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));
}
