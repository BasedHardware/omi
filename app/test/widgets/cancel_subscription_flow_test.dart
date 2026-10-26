import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/http_pool_manager.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/cancel_subscription_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/omi_theme.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/recording_analytics.dart';

/// The body prod's GET /v1/payments/retention-offer returns to an eligible $29.99/month reader.
const _eligibleOffer =
    '{"eligible":true,"percent_off":50,"duration_months":3,"regular_amount":2999,"discounted_amount":1499,"currency":"usd"}';
const _ineligibleOffer =
    '{"eligible":false,"percent_off":50,"duration_months":3,"regular_amount":null,"discounted_amount":null,"currency":null}';

/// Scripted backend for the cancel flow. Requests resolve on the widget test's fake clock.
class _Backend {
  static String offerBody = _eligibleOffer;
  static Duration offerLatency = const Duration(milliseconds: 400); // prod p50 is ~0.4s
  static final requests = <String>[];

  static Future<(int, String)> answer(String method, Uri url) async {
    requests.add('$method ${url.path}');
    if (method == 'GET' && url.path == '/v1/payments/retention-offer') {
      await Future<void>.delayed(offerLatency);
      return (200, offerBody);
    }
    if (method == 'DELETE' && url.path == '/v1/payments/subscription') {
      return (200, '{"status":"ok","message":"Subscription scheduled for cancellation."}');
    }
    return (404, '{"detail":"Not Found"}');
  }
}

class _CannedHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _CannedHttpClient();
}

class _CannedHttpClient implements HttpClient {
  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async => _CannedRequest(method, url);

  // Set by HttpPoolManager's constructor.
  @override
  int? maxConnectionsPerHost = 15;

  @override
  Duration idleTimeout = const Duration(seconds: 15);

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('canned client does not implement ${invocation.memberName}');
}

class _CannedRequest implements HttpClientRequest {
  _CannedRequest(this.method, this.uri);

  @override
  final String method;

  @override
  final Uri uri;

  @override
  HttpHeaders get headers => _CannedHttpHeaders();

  @override
  bool followRedirects = false;

  @override
  int maxRedirects = 5;

  @override
  bool persistentConnection = true;

  @override
  int contentLength = -1;

  @override
  Future<void> addStream(Stream<List<int>> stream) => stream.drain<void>();

  @override
  Future<HttpClientResponse> close() async {
    final (status, body) = await _Backend.answer(method, uri);
    return _CannedResponse(status, body);
  }

  @override
  void abort([Object? error, StackTrace? stackTrace]) {}

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('canned request does not implement ${invocation.memberName}');
}

class _CannedResponse extends Stream<List<int>> implements HttpClientResponse {
  _CannedResponse(this.statusCode, this.body);

  @override
  final int statusCode;

  final String body;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int> data)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream<List<int>>.fromIterable([utf8.encode(body)])
        .listen(onData, onError: onError, onDone: onDone, cancelOnError: cancelOnError);
  }

  @override
  HttpHeaders get headers => _CannedHttpHeaders();

  @override
  String get reasonPhrase => '';

  @override
  bool get isRedirect => false;

  @override
  List<RedirectInfo> get redirects => const [];

  @override
  bool get persistentConnection => true;

  @override
  int get contentLength => utf8.encode(body).length;

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('canned response does not implement ${invocation.memberName}');
}

class _CannedHttpHeaders implements HttpHeaders {
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

UserSubscriptionResponse _monthlySubscriber() => UserSubscriptionResponse(
      subscription: Subscription(
        plan: PlanType.unlimited,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_test_monthly',
        currentPeriodEnd: DateTime.utc(2026, 11, 20).millisecondsSinceEpoch ~/ 1000,
      ),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    );

/// PostHog keeps names containing "subscri" (and a few other substrings) at 100%; every other
/// name is sampled at 2% by distinct_id. See web/admin/docs/posthog-events.md, "Ingestion sampling".
bool _keptUnsampled(String eventName) => eventName.toLowerCase().contains('subscri');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late RecordingAnalytics analytics;
  var testHost = 0;

  setUpAll(() {
    // Construct the pooled client under the canned overrides: no request leaves the test.
    HttpOverrides.runWithHttpOverrides(() => HttpPoolManager.instance, _CannedHttpOverrides());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.578', buildNumber: '1', buildSignature: '');
    // HttpPoolManager shares in-flight GETs by URL; a host per test keeps one test's unfinished
    // request from answering the next.
    Env.overrideApiBaseUrl('http://cancel-flow-${++testHost}.test/');
    PlatformManager.initializeForLocalHarness();
    _Backend.offerBody = _eligibleOffer;
    _Backend.offerLatency = const Duration(milliseconds: 400);
    _Backend.requests.clear();
    analytics = RecordingAnalytics();
    AnalyticsManager.configure(analytics.adapter);
    await AnalyticsManager.init();
  });

  tearDown(() {
    Env.clearApiBaseUrlOverrideForTesting();
    AnalyticsManager.resetForTesting();
  });

  Future<List<String>> events() async {
    await AnalyticsManager.flushPending(force: true);
    return analytics.names;
  }

  /// Opens the flow from Settings the way plans_sheet.dart does and picks "Too expensive".
  Future<void> openAndPickReason(WidgetTester tester) async {
    final usage = UsageProvider(subscriptionRequest: () async => _monthlySubscriber());
    await usage.fetchSubscription();
    late BuildContext home;
    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: usage,
        child: MaterialApp(
          theme: buildOmiTheme(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Builder(builder: (context) {
            home = context;
            return const Scaffold(body: Text('settings'));
          }),
        ),
      ),
    );
    CancelSubscriptionFlow.show(home);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Too expensive'));
    await tester.pump();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
  }

  testWidgets('the last step has the stay offer the moment it appears', (tester) async {
    await openAndPickReason(tester);
    // The reader spends a second on the feedback step, longer than the backend takes to answer.
    await tester.pump(const Duration(seconds: 1));

    await tester.tap(find.text('Skip for Now'));
    await tester.pump(); // the last step is pushed (offstage for one frame)
    await tester.pump(); // and on screen, before any time passes

    expect(find.text('Just a moment, please'), findsOneWidget);
    expect(find.text('Stay for 50% off'), findsOneWidget);
    expect(find.text('Keep Subscription'), findsNothing, reason: 'no button swaps under the thumb');
    await tester.pumpAndSettle();
    expect(find.textContaining(r'$14.99'), findsOneWidget);
    expect(_Backend.requests.where((r) => r == 'GET /v1/payments/retention-offer'), hasLength(1));
    expect(await events(), contains('Subscription Retention Offer Shown'));
    analytics.expectSingle('Subscription Retention Offer Shown', {'reason': 'too_expensive', 'percent_off': 50});
  });

  testWidgets('cancelling with the offer on screen records the decline, unsampled', (tester) async {
    await openAndPickReason(tester);
    await tester.tap(find.text('Skip for Now'));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Stay for 50% off'), findsOneWidget);

    await tester.tap(find.text('Cancel Subscription'));
    await tester.pumpAndSettle();

    expect(find.text('settings'), findsOneWidget, reason: 'the flow closes after the cancel succeeds');
    final names = await events();
    expect(
      names.where((name) => name.contains('Retention') || name == 'Subscription Cancel Confirmed'),
      ['Subscription Retention Offer Shown', 'Subscription Retention Offer Declined', 'Subscription Cancel Confirmed'],
    );
    analytics.expectSingle('Subscription Retention Offer Declined', {'reason': 'too_expensive', 'percent_off': 50});
    final sampled = names.where((name) => name.contains('Retention') && !_keptUnsampled(name));
    expect(sampled, isEmpty, reason: 'PostHog keeps only 2% of these names');
  });

  testWidgets('a slow answer still shows the offer when it lands', (tester) async {
    _Backend.offerLatency = const Duration(seconds: 5);
    await openAndPickReason(tester);
    await tester.tap(find.text('Skip for Now'));
    await tester.pumpAndSettle();
    expect(find.text('Keep Subscription'), findsOneWidget);
    expect(find.text('Stay for 50% off'), findsNothing);

    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
    expect(find.text('Stay for 50% off'), findsOneWidget);
    analytics.expectSingle('Subscription Retention Offer Shown', {'reason': 'too_expensive', 'percent_off': 50});
  });

  testWidgets('an ineligible reader keeps the plain last step', (tester) async {
    _Backend.offerBody = _ineligibleOffer;
    await openAndPickReason(tester);
    await tester.pump(const Duration(seconds: 1));
    await tester.tap(find.text('Skip for Now'));
    await tester.pumpAndSettle();

    expect(find.text('Keep Subscription'), findsOneWidget);
    expect(find.text('Stay for 50% off'), findsNothing);
    expect((await events()).where((name) => name.contains('Retention')), isEmpty);
  });
}
