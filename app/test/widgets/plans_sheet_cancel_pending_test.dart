import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

Map<String, dynamic> _price(String planId, String title, String interval, int amount) => {
      'id': 'price_${planId}_$interval',
      'plan_id': planId,
      'title': title,
      'interval': interval,
      'unit_amount': amount,
      'price_string': '\$${amount ~/ 100}/${interval == 'year' ? 'yr' : 'mo'}',
      'is_active': false,
    };

class _Usage extends UsageProvider {
  final List<String> sessions = [];
  final List<String> upgrades = [];
  Map<String, dynamic>? sessionResult;
  Object? sessionError;
  bool clearCancelOnFetch = false;

  @override
  Future<void> loadAvailablePlans() async {}

  @override
  Future<void> fetchSubscription() async {
    if (!clearCancelOnFetch || subscription == null) return;
    final current = subscription!;
    debugSetSubscription(
      UserSubscriptionResponse(
        subscription: Subscription(
          plan: current.subscription.plan,
          status: current.subscription.status,
          stripeSubscriptionId: current.subscription.stripeSubscriptionId,
          currentPriceId: current.subscription.currentPriceId,
          currentPeriodEnd: current.subscription.currentPeriodEnd,
          cancelAtPeriodEnd: false,
        ),
        transcriptionSecondsUsed: current.transcriptionSecondsUsed,
        transcriptionSecondsLimit: current.transcriptionSecondsLimit,
        wordsTranscribedUsed: current.wordsTranscribedUsed,
        wordsTranscribedLimit: current.wordsTranscribedLimit,
        insightsGainedUsed: current.insightsGainedUsed,
        insightsGainedLimit: current.insightsGainedLimit,
        availablePlans: current.availablePlans,
      ),
    );
  }

  @override
  Future<Map<String, dynamic>?> createUserCheckoutSession(
      {required String priceId, String? promotionCode, int? trialDays}) async {
    sessions.add(priceId);
    if (sessionError != null) throw sessionError!;
    return sessionResult;
  }

  @override
  Future<Map<String, dynamic>?> upgradeUserSubscription({required String priceId, String? promotionCode}) async {
    upgrades.add(priceId);
    return null;
  }
}

class _Harness extends StatefulWidget {
  const _Harness();

  @override
  State<_Harness> createState() => _HarnessState();
}

class _HarnessState extends State<_Harness> with TickerProviderStateMixin {
  late final AnimationController _wave = AnimationController(vsync: this);
  late final AnimationController _notes = AnimationController(vsync: this);
  late final AnimationController _arrow = AnimationController(vsync: this);

  @override
  void dispose() {
    _wave.dispose();
    _notes.dispose();
    _arrow.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PlansSheet(
      waveController: _wave,
      notesController: _notes,
      arrowController: _arrow,
      arrowAnimation: _arrow,
      readStorefrontGate: () async => false,
    );
  }
}

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 200, scrollable: find.byType(Scrollable).first);
  await tester.pump();
  await tester.tap(finder);
  await tester.pump();
}

Future<_Usage> _pump(
  WidgetTester tester, {
  Map<String, dynamic>? sessionResult,
  Object? sessionError,
  bool clearCancelOnFetch = false,
  bool omitPeriodEnd = false,
  Locale locale = const Locale('en'),
}) async {
  tester.view.physicalSize = const Size(430, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  final usage = _Usage()
    ..sessionResult = sessionResult
    ..sessionError = sessionError
    ..clearCancelOnFetch = clearCancelOnFetch;
  addTearDown(usage.dispose);
  usage.debugSetSubscription(
    UserSubscriptionResponse(
      subscription: Subscription(
        plan: PlanType.plus,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_1',
        currentPriceId: 'price_plus_month',
        currentPeriodEnd: omitPeriodEnd ? null : _periodEndSeconds,
        cancelAtPeriodEnd: true,
      ),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    ),
  );
  usage.debugSetAvailablePlans({
    'plans': <dynamic>[
      _price('plus', 'Plus', 'month', 1999),
      _price('plus', 'Plus', 'year', 17990),
      _price('unlimited_v2', 'Unlimited', 'month', 2999),
      _price('unlimited_v2', 'Unlimited', 'year', 23990),
    ],
  });

  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        locale: locale,
        home: const Scaffold(body: _Harness()),
      ),
    ),
  );
  await tester.pump();
  return usage;
}

/// 2026-11-03 00:00:00 UTC. Far-east and far-west zones put that instant on different
/// local calendar days, so the expected label is the local day of the same epoch
/// the sheet formats.
final int _periodEndSeconds = DateTime.utc(2026, 11, 3).millisecondsSinceEpoch ~/ 1000;

String _date(WidgetTester tester) {
  final context = tester.element(find.byType(PlansSheet));
  return OmiDateFormat.of(context).date(DateTime.fromMillisecondsSinceEpoch(_periodEndSeconds * 1000));
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('resubscribe uses the current price and replaces the ends line', (tester) async {
    final usage = await _pump(
      tester,
      clearCancelOnFetch: true,
      sessionResult: {'status': 'reactivated', 'message': 'ok', 'next_billing_date': _periodEndSeconds},
    );
    final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));
    final date = _date(tester);

    expect(find.text(l10n.yourPlanEndsOn('Plus', date)), findsOneWidget);
    expect(find.text(l10n.resubscribeNowNoChargeUntil(date)), findsOneWidget);
    expect(find.text(l10n.resubscribe), findsOneWidget);
    expect(find.byKey(const ValueKey('plans_sheet_resubscribe_button')), findsOneWidget);
    final plus = tester.widget<PlanOptionCard>(find.widgetWithText(PlanOptionCard, 'Plus'));
    expect(plus.isSelected, isTrue);
    expect(plus.price, contains('/mo'));

    await _tap(tester, find.byKey(const ValueKey('plans_sheet_resubscribe_button')));
    await tester.pump();

    expect(usage.sessions, ['price_plus_month']);
    expect(usage.upgrades, isEmpty);
    expect(find.text(l10n.yourPlanWillRenewOn('Plus', date)), findsWidgets);
    expect(find.text(l10n.yourPlanEndsOn('Plus', date)), findsNothing);
    expect(find.text(l10n.resubscribeNowNoChargeUntil(date)), findsNothing);
  });

  testWidgets('a missing end date uses the generic cancel line and no reassurance', (tester) async {
    await _pump(tester, omitPeriodEnd: true);
    final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));

    expect(find.text(l10n.subscriptionSetToCancel), findsOneWidget);
    expect(find.text(l10n.yourPlanEndsOn('Plus', '—')), findsNothing);
    expect(find.text(l10n.resubscribeNowNoChargeUntil('—')), findsNothing);
    expect(find.byKey(const ValueKey('plans_sheet_cancel_reassurance')), findsNothing);
    expect(find.text(l10n.resubscribe), findsOneWidget);
  });

  testWidgets('another price is refused before any request', (tester) async {
    final usage = await _pump(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));

    await _tap(tester, find.widgetWithText(PlanOptionCard, 'Omi Pro'));

    expect(find.text(l10n.resubscribeFirstToChangePlans), findsOneWidget);
    expect(usage.sessions, isEmpty);
    expect(usage.upgrades, isEmpty);

    await _tap(tester, find.byKey(const ValueKey('plans_sheet_resubscribe_button')));

    expect(usage.sessions, ['price_plus_month']);
  });

  testWidgets('a checkout failure stays on the sheet', (tester) async {
    final usage = await _pump(tester, sessionError: Exception('network'));
    final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));

    await _tap(tester, find.byKey(const ValueKey('plans_sheet_resubscribe_button')));

    expect(usage.sessions, ['price_plus_month']);
    expect(find.byKey(const ValueKey('plans_sheet_purchase_error')), findsOneWidget);
    expect(find.text(l10n.anErrorOccurredTryAgain), findsWidgets);
  });

  for (final locale in const [Locale('en'), Locale('de'), Locale('ar')]) {
    testWidgets('checkout 409 shows the localized existing-subscription reason in ${locale.languageCode}',
        (tester) async {
      const existing =
          'You already have a subscription. Manage your existing subscription instead of starting a new checkout.';
      await _pump(tester, sessionResult: {'error': true, 'status_code': 409, 'detail': existing}, locale: locale);
      final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));

      await _tap(tester, find.byKey(const ValueKey('plans_sheet_resubscribe_button')));

      expect(find.text(l10n.checkoutExistingSubscription), findsWidgets);
      expect(find.text(existing), findsNothing);
      expect(find.text(l10n.resubscribeFirstToChangePlans), findsNothing);
    });
  }
}
