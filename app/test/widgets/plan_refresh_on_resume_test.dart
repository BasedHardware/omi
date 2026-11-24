// The plan is re-read when the app resumes (Google Play or the Stripe portal may have changed it)
// and when Plans & Billing opens, so a cancel or resubscribe shows without relaunching the app.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans/play_plans_content.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/utils/platform/platform_manager.dart';

UserSubscriptionResponse _playPro({required bool cancelAtPeriodEnd}) => UserSubscriptionResponse(
      subscription: Subscription(
        plan: PlanType.unlimitedV2,
        status: SubscriptionStatus.active,
        provider: 'play',
        cancelAtPeriodEnd: cancelAtPeriodEnd,
        currentPeriodEnd: 1893456000,
      ),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    );

final _renewing = _playPro(cancelAtPeriodEnd: false);
final _ending = _playPro(cancelAtPeriodEnd: true);

class _Usage extends UsageProvider {
  _Usage({required super.subscriptionRequest, required super.now});

  @override
  Future<void> loadAvailablePlans() async {}
}

/// A server whose answer the test changes, as Google Play's notification would.
class _Server {
  UserSubscriptionResponse answer = _renewing;
  int reads = 0;
  DateTime clock = DateTime(2026, 11, 23, 12);

  late final usage = _Usage(
    subscriptionRequest: () async {
      reads++;
      return answer;
    },
    now: () => clock,
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

Future<_Server> _pump(WidgetTester tester, {Widget child = const _Sheet(), UserSubscriptionResponse? answer}) async {
  tester.view.physicalSize = const Size(430, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final server = _Server();
  if (answer != null) server.answer = answer;
  addTearDown(server.usage.dispose);
  server.usage.debugSetSubscription(_renewing);
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

  testWidgets('two resumes within 30 seconds read once', (tester) async {
    final server = await _pump(tester, child: const SizedBox());
    await server.usage.refreshOnResume(signedIn: true);
    server.clock = server.clock.add(const Duration(seconds: 29));
    await server.usage.refreshOnResume(signedIn: true);
    expect(server.reads, 1);
    server.clock = server.clock.add(const Duration(seconds: 1));
    await server.usage.refreshOnResume(signedIn: true);
    expect(server.reads, 2);
    await tester.pump(const Duration(minutes: 1));
    expect(server.reads, 2, reason: 'an ordinary resume schedules no follow-up read');
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
}
