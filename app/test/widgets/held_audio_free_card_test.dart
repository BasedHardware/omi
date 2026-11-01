import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/held_audio/processing_backlog_view.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../support/recording_analytics.dart';

// Synthetic owners on either side of the stable 10% copy holdout.
const _personalUid = 'synthetic-0';
const _holdoutUid = 'synthetic-32';
const _held = 6 * 3600 + 20 * 60;

UserSubscriptionResponse _subscription(PlanType plan) => UserSubscriptionResponse(
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    );

ProcessingBacklog _backlog(String state, {bool exhausted = false, int seconds = _held}) => ProcessingBacklog(
      state: state,
      budgetExhausted: exhausted,
      heldAudioCount: seconds > 0 ? 40 : 0,
      heldAudioSeconds: seconds,
      estimatedHours: seconds / 3600,
      estimatedPercent: 0,
    );

void main() {
  late RecordingAnalytics analytics;

  Future<void> signIn(String uid) async {
    SharedPreferences.setMockInitialValues({'uid': uid});
    await SharedPreferencesUtil.init();
  }

  setUp(() async {
    await signIn(_personalUid);
    PlatformManager.initializeForLocalHarness();
    analytics = RecordingAnalytics();
    AnalyticsManager.configure(analytics.adapter);
    await AnalyticsManager.init();
    final previous = OmiColors.active;
    OmiColors.active = OmiPalette.light;
    addTearDown(() => OmiColors.active = previous);
  });

  tearDown(AnalyticsManager.resetForTesting);

  Future<UsageProvider> pump(WidgetTester tester, PlanType plan, Widget child) async {
    final usage = UsageProvider();
    addTearDown(usage.dispose);
    usage.debugSetSubscription(_subscription(plan));
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
      ],
      child: MaterialApp(
        locale: const Locale('en'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: buildOmiTheme(brightness: Brightness.light),
        home: Scaffold(body: SingleChildScrollView(child: child)),
      ),
    ));
    await tester.pump();
    return usage;
  }

  AppLocalizations l10n(WidgetTester tester) => AppLocalizations.of(tester.element(find.byType(Scaffold)));

  test('the copy holdout is a stable ~10% hashed bucket', () {
    expect(heldAudioCopyHoldout(_holdoutUid), isTrue);
    expect(heldAudioCopyHoldout(_personalUid), isFalse);
    expect(heldAudioCopyHoldout(''), isFalse);
    final held = List.generate(5000, (i) => heldAudioCopyHoldout('owner-$i')).where((h) => h).length;
    expect(held, inInclusiveRange(400, 600));
  });

  for (final exhausted in [false, true]) {
    testWidgets('Free card is personal and offers only Upgrade (budget exhausted: $exhausted)', (tester) async {
      var upgrades = 0;
      await pump(
        tester,
        PlanType.basic,
        ProcessingBacklogView(
          backlog: _backlog('capped', exhausted: exhausted),
          surface: 'a',
          onUpgrade: () => upgrades++,
          phoneAction: const Text('phone-action'),
        ),
      );
      final text = l10n(tester);
      expect(find.text(text.processingFreeHeld('6h 20m')), findsOneWidget);
      expect(find.text(text.processingFreeUpgrade), findsOneWidget);
      expect(find.text(text.processingStored), findsNothing);
      // A Free owner under the monthly limit is never told the limit is reached.
      expect(find.text(text.processingPaused), findsNothing);
      expect(find.byKey(const Key('processing_backlog_process_a')), findsNothing);
      // Upgrade first, "Transcribe on this phone" second.
      final upgrade = tester.getTopLeft(find.byKey(const Key('processing_backlog_upgrade_a'))).dy;
      expect(upgrade, lessThan(tester.getTopLeft(find.text('phone-action')).dy));
      analytics.expectSingle('Held Audio Card Seen', {'surface': 'home', 'variant': 'personal', 'state': 'capped'});

      await tester.tap(find.byKey(const Key('processing_backlog_upgrade_a')));
      await tester.pump();
      expect(upgrades, 1);
      analytics.expectSingle('Held Audio Upgrade Tapped', {'surface': 'home', 'variant': 'personal'});
    });
  }

  testWidgets('Free holdout keeps the previous card and is labelled holdout', (tester) async {
    await signIn(_holdoutUid);
    await pump(
      tester,
      PlanType.basic,
      ProcessingBacklogView(backlog: _backlog('capped', exhausted: true), surface: 'b', onUpgrade: () {}),
    );
    final text = l10n(tester);
    expect(find.text(text.processingPaused), findsOneWidget);
    expect(find.text(text.processingStored), findsOneWidget);
    expect(find.text(text.processingFreeHeld('6h 20m')), findsNothing);
    analytics.expectSingle('Held Audio Card Seen', {'surface': 'live', 'variant': 'holdout'});
  });

  testWidgets('Free card with nothing held makes no waiting-recordings claim', (tester) async {
    await pump(
      tester,
      PlanType.basic,
      ProcessingBacklogView(backlog: _backlog('capped', exhausted: true, seconds: 0), surface: 'a', onUpgrade: () {}),
    );
    final text = l10n(tester);
    expect(find.text(text.processingPaused), findsOneWidget);
    expect(find.text(text.processingFreeStored), findsNothing);
    expect(find.text(text.processingFreeUpgrade), findsNothing);
    expect(find.text(text.processingStored), findsNothing);
  });

  testWidgets('Unlimited owner sees the process action, accurate copy and no Upgrade', (tester) async {
    await pump(
      tester,
      PlanType.unlimitedV2,
      ProcessingBacklogView(
          backlog: _backlog('waiting_choice'), surface: 'c', onUpgrade: () {}, onProcess: () async => true),
    );
    final text = l10n(tester);
    expect(find.text(text.processingStored), findsOneWidget);
    expect(find.text(text.processingFreeUpgrade), findsNothing);
    expect(find.byKey(const Key('processing_backlog_upgrade_c')), findsNothing);
    await tester.tap(find.byKey(const Key('processing_backlog_process_c')));
    await tester.pump();
    analytics
        .expectSingle('Held Audio Card Seen', {'surface': 'settings', 'variant': 'paid', 'state': 'waiting_choice'});
    analytics.expectSingle('Held Audio Process Tapped', {'surface': 'settings', 'variant': 'paid'});
  });

  testWidgets('Plus owner at the monthly limit keeps the paused copy and no Upgrade', (tester) async {
    await pump(
      tester,
      PlanType.plus,
      ProcessingBacklogView(backlog: _backlog('capped', exhausted: true), surface: 'a', onUpgrade: () {}),
    );
    final text = l10n(tester);
    expect(find.text(text.processingPaused), findsOneWidget);
    expect(find.text(text.processingStored), findsOneWidget);
    expect(find.byKey(const Key('processing_backlog_upgrade_a')), findsNothing);
  });

  testWidgets('a rebuild does not count the card as seen again', (tester) async {
    final usage = await pump(
      tester,
      PlanType.basic,
      ProcessingBacklogView(backlog: _backlog('capped'), surface: 'a', onUpgrade: () {}),
    );
    usage.debugSetSubscription(_subscription(PlanType.basic));
    await tester.pump();
    await tester.pump();
    expect(analytics.propertiesOf('Held Audio Card Seen'), hasLength(1));
  });

  testWidgets('legacy Free card and live banner use the personal copy', (tester) async {
    await pump(
      tester,
      PlanType.basic,
      Column(children: [
        HeldAudioCardView(
          atCap: true,
          seconds: _held,
          resetOn: DateTime(2026, 12, 1),
          phoneEligible: false,
          phoneChosen: false,
          onUpgrade: () {},
          onTranscribeOnPhone: () {},
          personal: true,
        ),
        HeldAudioLiveBannerView(
          phoneEligible: false,
          phoneChosen: false,
          onUpgrade: () {},
          onTranscribeOnPhone: () {},
          personal: true,
        ),
      ]),
    );
    final text = l10n(tester);
    expect(find.text(text.processingFreeHeld('6h 20m')), findsOneWidget);
    expect(find.text(text.processingFreeUpgrade), findsOneWidget);
    expect(find.text(text.processingFreeStored), findsOneWidget);
    expect(find.text(text.processingStored), findsNothing);
  });

  testWidgets('Free card Upgrade opens the plans sheet with the Unlimited plan', (tester) async {
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final usage = await pump(
      tester,
      PlanType.basic,
      HeldAudioHomeSection(gate: true, backlog: _backlog('capped')),
    );
    usage.debugSetAvailablePlans({
      'plans': <dynamic>[
        {
          'id': 'price_unlimited_v2_month',
          'plan_id': 'unlimited_v2',
          'title': 'Unlimited',
          'interval': 'month',
          'unit_amount': 2999,
          'price_string': '\$29.99/mo',
          'is_active': false,
        },
      ]
    });
    await tester.tap(find.byKey(const Key('processing_backlog_upgrade_a')));
    await tester.pumpAndSettle();
    expect(find.byType(PlansSheet), findsOneWidget);
    expect(find.textContaining('Unlimited'), findsWidgets);
  });
}
