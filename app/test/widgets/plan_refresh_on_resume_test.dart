// The plan is re-read when the app resumes (Google Play or the Stripe portal may have changed it)
// and when Plans & Billing opens, so a cancel or resubscribe shows without relaunching the app.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:in_app_purchase_platform_interface/in_app_purchase_platform_interface.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/play_billing_api.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/home/plan_refresh_on_resume.dart';
import 'package:omi/pages/settings/widgets/plans/play_plans_content.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/billing/play_billing.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../support/fake_play_billing.dart';

UserSubscriptionResponse _sub({
  PlanType plan = PlanType.unlimitedV2,
  String? provider = 'play',
  bool cancelAtPeriodEnd = false,
  PlayBillingConfig? play,
}) =>
    UserSubscriptionResponse(
      subscription: Subscription(
        plan: plan,
        status: SubscriptionStatus.active,
        provider: provider,
        cancelAtPeriodEnd: cancelAtPeriodEnd,
        currentPeriodEnd: plan.isPaid ? 1893456000 : null,
      ),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      playBilling: play,
    );

final _renewing = _sub();
final _ending = _sub(cancelAtPeriodEnd: true);

class _Usage extends UsageProvider {
  _Usage({required super.subscriptionRequest, required super.now, super.playBilling});

  @override
  Future<void> loadAvailablePlans() async {}
}

/// A server whose answer the test changes, as Google Play's notification would. Each GET answers
/// with what the server held when the request arrived, even if [gate] holds the reply back.
class _Server {
  _Server({this.billing});

  final PlayBilling? billing;
  UserSubscriptionResponse? answer = _renewing; // null: the read fails
  Completer<void>? gate;
  int reads = 0;
  DateTime clock = DateTime(2026, 11, 23, 12);

  late final usage = _Usage(
    subscriptionRequest: () async {
      reads++;
      final reply = answer;
      final held = gate;
      if (held != null) await held.future;
      return reply;
    },
    now: () => clock,
    playBilling: billing,
  );
}

class _Sheet extends StatefulWidget {
  const _Sheet();

  @override
  State<_Sheet> createState() => _SheetState();
}

class _SheetState extends State<_Sheet> with SingleTickerProviderStateMixin {
  late final AnimationController _animation = AnimationController(vsync: this);

  @override
  void dispose() {
    _animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PlansSheet(
        waveController: _animation,
        notesController: _animation,
        arrowController: _animation,
        arrowAnimation: _animation,
        readStorefrontGate: () async => false,
      );
}

Future<_Server> _pump(
  WidgetTester tester, {
  Widget child = const _Sheet(),
  UserSubscriptionResponse? answer,
  UserSubscriptionResponse? held,
  PlayBilling? billing,
}) async {
  tester.view.physicalSize = const Size(430, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final server = _Server(billing: billing);
  if (answer != null) server.answer = answer;
  addTearDown(server.usage.dispose);
  server.usage.debugSetSubscription(held ?? _renewing);
  await tester.pumpWidget(
    ChangeNotifierProvider<UsageProvider>.value(
      value: server.usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(body: child),
      ),
    ),
  );
  return server;
}

final _willRenew = find.textContaining('will renew on');
final _ends = find.textContaining('plan ends');

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TranscriptionAllowanceCache.clear();
    Env.overrideApiBaseUrl('http://127.0.0.1:1/');
    PlatformManager.initializeForLocalHarness();
  });

  tearDown(() {
    TranscriptionAllowanceCache.clear();
    Env.clearApiBaseUrlOverrideForTesting();
  });

  testWidgets('opening the sheet re-reads the plan and updates in place, no loading state', (tester) async {
    final server = await _pump(tester, answer: _ending);
    // First frame: the last answer, not a skeleton, while the opening read is in flight.
    expect(_willRenew, findsOneWidget);
    expect(find.byType(PlayPlansLoading), findsNothing);
    await tester.pumpAndSettle();
    expect(server.reads, 1);
    expect(_ends, findsOneWidget);
    expect(_willRenew, findsNothing);
  });

  testWidgets('a resume reads once and the sheet changes from will renew to ends without relaunch', (tester) async {
    final server = await _pump(tester);
    await tester.pumpAndSettle();
    expect(server.reads, 1, reason: 'the opening read');
    expect(_willRenew, findsOneWidget);

    server.answer = _ending; // cancelled in Google Play while the app was away
    await server.usage.refreshOnResume(signedIn: true);
    await tester.pumpAndSettle();
    expect(server.reads, 2);
    expect(_ends, findsOneWidget);

    server.answer = _renewing; // resubscribed in Google Play
    server.clock = server.clock.add(UsageProvider.resumeRefreshInterval);
    await server.usage.refreshOnResume(signedIn: true);
    await tester.pumpAndSettle();
    expect(server.reads, 3);
    expect(_willRenew, findsOneWidget);
  });

  testWidgets('two resumes within 2 minutes read once', (tester) async {
    final server = await _pump(tester, child: const SizedBox());
    await server.usage.refreshOnResume(signedIn: true);
    server.clock = server.clock.add(const Duration(minutes: 1, seconds: 59));
    await server.usage.refreshOnResume(signedIn: true);
    expect(server.reads, 1);
    server.clock = server.clock.add(const Duration(seconds: 1));
    await server.usage.refreshOnResume(signedIn: true);
    expect(server.reads, 2);
    await tester.pump(const Duration(minutes: 1));
    expect(server.reads, 2, reason: 'an ordinary resume schedules no follow-up read');
  });

  testWidgets('a failed resume read does not hold back the next resume', (tester) async {
    final server = await _pump(tester, child: const SizedBox());
    server.answer = null;
    await server.usage.refreshOnResume(signedIn: true);
    expect(server.reads, 1);
    server.answer = _ending;
    server.clock = server.clock.add(const Duration(seconds: 5));
    await server.usage.refreshOnResume(signedIn: true);
    expect(server.reads, 2);
    expect(server.usage.subscription!.subscription.cancelAtPeriodEnd, isTrue);
    server.clock = server.clock.add(const Duration(seconds: 5));
    await server.usage.refreshOnResume(signedIn: true);
    expect(server.reads, 2, reason: 'the successful read starts the 2-minute window');
  });

  testWidgets('a failed read on sheet open keeps the plan on screen, no error state', (tester) async {
    final server = await _pump(tester);
    server.answer = null;
    await tester.pumpAndSettle();
    expect(server.reads, 1);
    expect(_willRenew, findsOneWidget);
    expect(find.byKey(const Key('play_manage_subscription')), findsOneWidget);
    expect(find.byType(PlayPlansLoading), findsNothing);
    expect(find.byType(OmiErrorState), findsNothing);
  });

  testWidgets('two fresh reads requested during a stale read share one later read', (tester) async {
    final server = await _pump(tester, child: const SizedBox());
    server.gate = Completer<void>();
    final stale = server.usage.fetchSubscription();
    server.answer = _ending;
    final a = server.usage.fetchSubscription(fresh: true);
    final b = server.usage.fetchSubscription(fresh: true);
    expect(server.reads, 1);
    server.gate!.complete();
    server.gate = null;
    await Future.wait([stale, a, b]);
    expect(server.reads, 2);
    expect(server.usage.subscription!.subscription.cancelAtPeriodEnd, isTrue);
  });

  testWidgets('the observer reads on resume when signed in and not when signed out', (tester) async {
    for (final signedIn in [true, false]) {
      final server = await _pump(
        tester,
        child: PlanRefreshOnResume(isSignedIn: (_) => signedIn, child: const SizedBox()),
      );
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump();
      expect(server.reads, 0, reason: 'leaving the app reads nothing');
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(server.reads, signedIn ? 1 : 0);
      await tester.pumpWidget(const SizedBox());
    }
  });

  testWidgets('Google Play page that fails to open leaves the next resume ordinary', (tester) async {
    final server = await _pump(
      tester,
      child: PlayPlansContent(analyticsSource: 'test', openUrl: (_) async => false),
    );
    await server.usage.refreshOnResume(signedIn: true);
    await tester.tap(find.byKey(const Key('play_manage_subscription')));
    await tester.pump();
    server.clock = server.clock.add(const Duration(seconds: 10));
    await server.usage.refreshOnResume(signedIn: true);
    await tester.pump(const Duration(seconds: 10));
    expect(server.reads, 1, reason: 'throttled, and no follow-up read');
    await tester.pump(const Duration(seconds: 5)); // let the error toast go
  });

  testWidgets('signing out cancels the pending Google Play follow-up read', (tester) async {
    final server = await _pump(
      tester,
      child: PlayPlansContent(analyticsSource: 'test', openUrl: (_) async => true),
    );
    await tester.tap(find.byKey(const Key('play_manage_subscription')));
    await tester.pump();
    await server.usage.refreshOnResume(signedIn: true);
    expect(server.reads, 1);
    server.usage.clearUserData();
    await tester.pump(const Duration(minutes: 1));
    expect(server.reads, 1);
  });

  testWidgets('signed out: a resume reads nothing, even after Google Play', (tester) async {
    final server = await _pump(tester, child: const SizedBox());
    await server.usage.refreshOnResume(signedIn: false);
    server.usage.markOpenedPlayManage();
    await server.usage.refreshOnResume(signedIn: false);
    await tester.pump(const Duration(minutes: 1));
    expect(server.reads, 0);
  });

  testWidgets('returning from Google Play reads on resume and exactly once more 5 seconds later', (tester) async {
    final opened = <Uri>[];
    final server = await _pump(
      tester,
      child: PlayPlansContent(
        analyticsSource: 'test',
        openUrl: (uri) async {
          opened.add(uri);
          return true;
        },
      ),
    );
    // A resume a moment ago does not hold back the read after Google Play.
    await server.usage.refreshOnResume(signedIn: true);
    expect(server.reads, 1);

    await tester.tap(find.byKey(const Key('play_manage_subscription')));
    await tester.pump();
    expect(opened.single.host, 'play.google.com');

    server.clock = server.clock.add(const Duration(seconds: 10));
    await server.usage.refreshOnResume(signedIn: true);
    expect(server.reads, 2, reason: 'the resume read, before Play has told the server');

    server.answer = _ending; // Play's notification lands a few seconds later
    await tester.pump(const Duration(seconds: 4));
    expect(server.reads, 2);
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    expect(server.reads, 3);
    expect(_ends, findsOneWidget);

    await tester.pump(const Duration(minutes: 1));
    expect(server.reads, 3, reason: 'one follow-up only, no polling');
  });
  group('Google Play purchase', () {
    late FakePlayPlatform platform;
    late PlayBilling billing;
    late Completer<PlayVerifyResult>? verifyGate;
    late _Server server;
    final free = _sub(plan: PlanType.basic, provider: null, play: playConfig);
    final pro = _sub(play: playConfig);

    Future<void> pumpPurchaser(WidgetTester tester) async {
      platform = FakePlayPlatform();
      verifyGate = null;
      billing = PlayBilling(
        platform: () => platform,
        store: MemoryTokenStore(),
        verify: (token, product) async {
          final held = verifyGate;
          final result = held == null ? const PlayVerifyResult('active') : await held.future;
          server.answer = pro; // the server grants the plan when verify commits
          return result;
        },
      );
      addTearDown(billing.dispose);
      server = await _pump(
        tester,
        billing: billing,
        held: free,
        answer: free,
        child: const PlayPlansContent(analyticsSource: 'test'),
      );
      await server.usage.fetchSubscription(); // Play config and offers, as AppShell's startup read
      await tester.pumpAndSettle();
      server.reads = 0;
      expect(find.byKey(const Key('play_subscribe')), findsOneWidget);
    }

    testWidgets('a resume read in flight with the old Free plan does not stand in for the read after verify',
        (tester) async {
      await pumpPurchaser(tester);
      // The Play sheet closing resumes the app; that read leaves before verify and answers Free late.
      server.gate = Completer<void>();
      unawaited(server.usage.refreshOnResume(signedIn: true));
      expect(server.reads, 1);

      platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
      await tester.tap(find.byKey(const Key('play_subscribe')));
      await tester.pump();
      await tester.pump();
      expect(server.answer!.subscription.plan, PlanType.unlimitedV2, reason: 'verify has returned');

      final stale = server.gate!;
      server.gate = null;
      stale.complete(); // the stale Free answer lands now
      await tester.pumpAndSettle();

      expect(server.reads, 2);
      expect(server.usage.subscription!.subscription.plan, PlanType.unlimitedV2);
      await tester.pump(const Duration(seconds: 5)); // let the success toast go
    }, variant: TargetPlatformVariant.only(TargetPlatform.android));

    testWidgets('a resume while a Play purchase is being confirmed reads nothing', (tester) async {
      await pumpPurchaser(tester);
      verifyGate = Completer<PlayVerifyResult>();
      platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
      await tester.tap(find.byKey(const Key('play_subscribe')));
      await tester.pump();
      expect(billing.busy, isTrue);

      await server.usage.refreshOnResume(signedIn: true);
      expect(server.reads, 0);

      verifyGate!.complete(const PlayVerifyResult('active'));
      await tester.pumpAndSettle();
      expect(server.reads, 1, reason: "the purchase's own read");
      expect(server.usage.subscription!.subscription.plan, PlanType.unlimitedV2);
      await tester.pump(const Duration(seconds: 5));
    }, variant: TargetPlatformVariant.only(TargetPlatform.android));
  });
}
