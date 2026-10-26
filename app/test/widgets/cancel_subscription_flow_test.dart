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
import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';
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
  static int offerStatus = 200;
  static Duration offerLatency = const Duration(milliseconds: 400); // prod p50 is ~0.4s
  // Statuses answered in order; the last one repeats. The app retries a 5xx once.
  static List<int> acceptStatuses = [200];
  static List<int> cancelStatuses = [200];
  static final requests = <String>[];

  static int _next(List<int> statuses) => statuses.length > 1 ? statuses.removeAt(0) : statuses.single;

  static Future<(int, String)> answer(String method, Uri url) async {
    requests.add('$method ${url.path}');
    if (method == 'GET' && url.path == '/v1/payments/retention-offer') {
      await Future<void>.delayed(offerLatency);
      return (offerStatus, offerStatus == 200 ? offerBody : '{"detail":"Internal Server Error"}');
    }
    if (method == 'POST' && url.path == '/v1/payments/retention-offer') {
      final status = _next(acceptStatuses);
      return (status, status == 200 ? _eligibleOffer : '{"detail":"Offer not available: in_progress"}');
    }
    if (method == 'DELETE' && url.path == '/v1/payments/subscription') {
      final status = _next(cancelStatuses);
      return status == 200
          ? (200, '{"status":"ok","message":"Subscription scheduled for cancellation."}')
          : (status, '{"detail":"Could not cancel subscription. Please try again."}');
    }
    return (404, '{"detail":"Not Found"}');
  }

  static int count(String request) => requests.where((r) => r == request).length;
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
    _Backend.offerStatus = 200;
    _Backend.offerLatency = const Duration(milliseconds: 400);
    _Backend.acceptStatuses = [200];
    _Backend.cancelStatuses = [200];
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

  Future<Iterable<String>> offerEvents() async => (await events()).where((name) => name.contains('Retention'));

  OmiButton button(WidgetTester tester, String label) =>
      tester.widget<OmiButton>(find.widgetWithText(OmiButton, label));

  /// Opens the flow from Settings the way plans_sheet.dart does and picks "Too expensive".
  /// Returns the flow's result: true when the subscription was cancelled.
  Future<Future<bool?>> openAndPickReason(WidgetTester tester) async {
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
    final result = CancelSubscriptionFlow.show(home);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Too expensive'));
    await tester.pump();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    return result;
  }

  /// Feedback step -> last step, checked on its first frame on screen, before any time passes.
  Future<void> skipToLastStep(WidgetTester tester) async {
    await tester.tap(find.text('Skip for Now'));
    await tester.pump(); // the last step is pushed (offstage for one frame)
    await tester.pump(); // and on screen
    expect(find.text('Just a moment, please'), findsOneWidget);
  }

  testWidgets('the last step has the stay offer the moment it appears', (tester) async {
    await openAndPickReason(tester);
    // The reader spends a second on the feedback step, longer than the backend takes to answer.
    await tester.pump(const Duration(seconds: 1));
    await skipToLastStep(tester);

    expect(find.text('Stay for 50% off'), findsOneWidget);
    expect(find.text('Keep Subscription'), findsNothing, reason: 'no button swaps under the thumb');
    await tester.pumpAndSettle();
    expect(find.textContaining(r'$14.99'), findsOneWidget);
    expect(_Backend.count('GET /v1/payments/retention-offer'), 1);
    expect(await offerEvents(), ['Subscription Retention Offer Shown']);
    analytics.expectSingle('Subscription Retention Offer Shown', {'reason': 'too_expensive', 'percent_off': 50});
  });

  testWidgets('a late answer fills a slot the reader could never tap', (tester) async {
    _Backend.offerLatency = const Duration(milliseconds: 2800); // inside the 3 s limit
    await openAndPickReason(tester);
    await skipToLastStep(tester);

    expect(find.text('Keep Subscription'), findsNothing);
    expect(find.text('Stay for 50% off'), findsNothing);
    expect(button(tester, 'Loading…').onPressed, isNull, reason: 'the pending slot is not an action');
    expect(button(tester, 'Cancel Subscription').onPressed, isNotNull, reason: 'cancel works while pending');
    for (var i = 0; i < 30 && find.text('Stay for 50% off').evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text('Keep Subscription'), findsNothing, reason: 'Keep never shows before the offer');
    }
    expect(button(tester, 'Stay for 50% off').onPressed, isNotNull);
    await tester.pumpAndSettle();
    expect(await offerEvents(), ['Subscription Retention Offer Shown']);
  });

  testWidgets('an answer after the time limit leaves Keep in place', (tester) async {
    _Backend.offerLatency = const Duration(seconds: 5);
    await openAndPickReason(tester);
    await skipToLastStep(tester);
    expect(find.text('Loading…'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3)); // past the limit, counted from when the flow opened
    expect(button(tester, 'Keep Subscription').onPressed, isNotNull);

    await tester.pump(const Duration(seconds: 3)); // the eligible answer arrives after all
    await tester.pumpAndSettle();
    expect(find.text('Keep Subscription'), findsOneWidget, reason: 'an action the reader can tap never changes');
    expect(find.text('Stay for 50% off'), findsNothing);
    expect(await offerEvents(), isEmpty);
  });

  testWidgets('cancelling while the offer is pending goes straight through', (tester) async {
    _Backend.offerLatency = const Duration(seconds: 5);
    final result = await openAndPickReason(tester);
    await skipToLastStep(tester);
    expect(find.text('Loading…'), findsOneWidget);

    await tester.tap(find.text('Cancel Subscription'));
    await tester.pumpAndSettle();
    expect(find.text('settings'), findsOneWidget);
    expect(await result, isTrue);
    expect(_Backend.count('DELETE /v1/payments/subscription'), 1);

    await tester.pump(const Duration(seconds: 5)); // the answer lands after the flow closed
    expect(await events(), contains('Subscription Cancel Confirmed'));
    expect(await offerEvents(), isEmpty, reason: 'the reader never saw the offer');
  });

  testWidgets('a decline counts only once the cancellation goes through, unsampled', (tester) async {
    _Backend.cancelStatuses = [500, 500, 200]; // the app retries a 5xx once, so the first tap fails
    final result = await openAndPickReason(tester);
    await tester.pump(const Duration(seconds: 1));
    await skipToLastStep(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Cancel Subscription'));
    await tester.pumpAndSettle();
    expect(find.text('Just a moment, please'), findsOneWidget, reason: 'a failed cancel stays on the step');
    expect(await offerEvents(), ['Subscription Retention Offer Shown']);
    await tester.pump(OmiFeedbackTiming.error + const Duration(seconds: 1)); // the error toast clears
    await tester.pumpAndSettle();

    await tester.tap(find.text('Cancel Subscription'));
    await tester.pumpAndSettle();
    expect(find.text('settings'), findsOneWidget);
    expect(await result, isTrue);
    expect(_Backend.count('DELETE /v1/payments/subscription'), 3);
    final names = await offerEvents();
    expect(names, ['Subscription Retention Offer Shown', 'Subscription Retention Offer Declined']);
    analytics.expectSingle('Subscription Retention Offer Declined', {'reason': 'too_expensive', 'percent_off': 50});
    expect(names.where((name) => !_keptUnsampled(name)), isEmpty, reason: 'PostHog keeps only 2% of these names');
  });

  testWidgets('an acceptance counts only once the backend applies the offer', (tester) async {
    _Backend.acceptStatuses = [409, 200]; // the offer is busy for this customer, then applies
    final result = await openAndPickReason(tester);
    await tester.pump(const Duration(seconds: 1));
    await skipToLastStep(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Stay for 50% off'));
    await tester.pumpAndSettle();
    expect(find.text('Just a moment, please'), findsOneWidget, reason: 'a failed acceptance stays on the step');
    expect(await offerEvents(), ['Subscription Retention Offer Shown']);
    await tester.pump(OmiFeedbackTiming.error + const Duration(seconds: 1)); // the error toast clears
    await tester.pumpAndSettle();

    await tester.tap(find.text('Stay for 50% off'));
    await tester.pumpAndSettle();
    expect(find.text('settings'), findsOneWidget);
    expect(await result, isFalse, reason: 'the plan was kept');
    expect(_Backend.count('POST /v1/payments/retention-offer'), 2);
    expect(_Backend.count('DELETE /v1/payments/subscription'), 0, reason: 'taking the offer never cancels');
    expect(await offerEvents(), ['Subscription Retention Offer Shown', 'Subscription Retention Offer Accepted']);
    analytics.expectSingle('Subscription Retention Offer Accepted', {'reason': 'too_expensive', 'percent_off': 50});
    expect(await events(), isNot(contains('Subscription Cancel Confirmed')));
  });

  testWidgets('an ineligible reader keeps the plain last step', (tester) async {
    _Backend.offerBody = _ineligibleOffer;
    await openAndPickReason(tester);
    await tester.pump(const Duration(seconds: 1));
    await skipToLastStep(tester);

    expect(button(tester, 'Keep Subscription').onPressed, isNotNull);
    expect(find.text('Stay for 50% off'), findsNothing);
    expect(await offerEvents(), isEmpty);
  });

  testWidgets('a failed lookup falls back to the plain last step', (tester) async {
    _Backend.offerStatus = 500; // retried once, then given up
    await openAndPickReason(tester);
    await tester.pump(const Duration(seconds: 2));
    await skipToLastStep(tester);

    expect(button(tester, 'Keep Subscription').onPressed, isNotNull);
    expect(find.text('Stay for 50% off'), findsNothing);
    expect(_Backend.count('GET /v1/payments/retention-offer'), 2);
    expect(await offerEvents(), isEmpty);
  });
}
