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
import 'package:omi/utils/platform/platform_manager.dart';

Map<String, dynamic> _price(String planId, String title, String interval, int amount, {bool active = false}) => {
      'id': 'price_${planId}_$interval',
      'plan_id': planId,
      'title': title,
      'interval': interval,
      'unit_amount': amount,
      'price_string': '\$${amount ~/ 100}/${interval == 'year' ? 'yr' : 'mo'}',
      'is_active': active,
    };

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
    return PlansSheet(waveController: _wave, notesController: _notes, arrowController: _arrow, arrowAnimation: _arrow);
  }
}

Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pump();
  await tester.tap(finder);
  await tester.pump();
}

Future<void> _pumpPlansSheet(
  WidgetTester tester, {
  required Subscription subscription,
  required List<Map<String, dynamic>> plans,
}) async {
  await tester.binding.setSurfaceSize(const Size(430, 2400));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  final usage = UsageProvider();
  addTearDown(usage.dispose);
  usage.debugSetSubscription(
    UserSubscriptionResponse(
      subscription: subscription,
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    ),
  );
  usage.debugSetAvailablePlans({
    'plans': <dynamic>[...plans]
  });

  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
      ],
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: [Locale('en')],
        home: Scaffold(body: _Harness()),
      ),
    ),
  );
  await tester.pump();
}

bool _selected(WidgetTester tester, String title) =>
    tester.widget<PlanOptionCard>(find.widgetWithText(PlanOptionCard, title)).isSelected;

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('the current plan card can be selected again after picking another tier', (tester) async {
    await _pumpPlansSheet(
      tester,
      subscription: Subscription(
        plan: PlanType.plus,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_1',
        currentPriceId: 'price_plus_month',
      ),
      plans: [
        _price('plus', 'Plus', 'month', 900, active: true),
        _price('plus', 'Plus', 'year', 9000),
        _price('unlimited_v2', 'Unlimited', 'month', 1900),
        _price('unlimited_v2', 'Unlimited', 'year', 19000),
      ],
    );
    final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));
    final upgradeButton = find.byKey(const ValueKey('plans_sheet_upgrade_button'));

    await _tapVisible(tester, find.widgetWithText(PlanOptionCard, 'Omi Pro'));
    expect(_selected(tester, 'Omi Pro'), isTrue);

    await _tapVisible(tester, find.text(l10n.billingMonthly));
    expect(_selected(tester, 'Omi Pro'), isTrue);
    expect(upgradeButton, findsOneWidget);

    await _tapVisible(tester, find.widgetWithText(PlanOptionCard, 'Plus'));
    expect(_selected(tester, 'Plus'), isTrue);
    expect(_selected(tester, 'Omi Pro'), isFalse);
    expect(upgradeButton, findsNothing, reason: 'nothing to switch to on the price already paid');

    await _tapVisible(tester, find.text(l10n.billingYearly));
    expect(_selected(tester, 'Plus'), isTrue);
    expect(upgradeButton, findsOneWidget);
  });

  testWidgets('a tier with no price for the chosen period hands the selection to a visible tier', (tester) async {
    await _pumpPlansSheet(
      tester,
      subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
      plans: [
        _price('plus', 'Plus', 'month', 900),
        _price('plus', 'Plus', 'year', 9000),
        _price('unlimited_v2', 'Unlimited', 'year', 19000),
      ],
    );
    final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));

    await _tapVisible(tester, find.widgetWithText(PlanOptionCard, 'Omi Pro'));
    expect(_selected(tester, 'Omi Pro'), isTrue);

    await _tapVisible(tester, find.text(l10n.billingMonthly));
    expect(find.widgetWithText(PlanOptionCard, 'Omi Pro'), findsNothing);
    expect(_selected(tester, 'Plus'), isTrue, reason: 'the hidden Omi Pro card must not stay selected');
  });

  testWidgets('an Operator subscriber sees Omi Pro first, on Desktop, and may switch to it', (tester) async {
    await _pumpPlansSheet(
      tester,
      subscription: Subscription(
        plan: PlanType.operator,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_1',
        currentPriceId: 'price_operator_month',
      ),
      plans: [
        _price('operator', 'Pro', 'month', 4999, active: true),
        _price('operator', 'Pro', 'year', 44999),
        _price('unlimited_v2', 'Unlimited', 'month', 2999),
        _price('unlimited_v2', 'Unlimited', 'year', 26991),
      ],
    );
    final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));
    await _tapVisible(tester, find.text(l10n.billingMonthly));

    final cards = tester.widgetList<PlanOptionCard>(find.byType(PlanOptionCard)).toList();
    expect(cards.map((card) => card.title), ['Omi Pro', 'Operator']);
    expect(cards.map((card) => card.desktopAccess), [true, true]);

    await _tapVisible(tester, find.widgetWithText(PlanOptionCard, 'Omi Pro'));
    expect(find.byKey(const ValueKey('plans_sheet_upgrade_button')), findsOneWidget);
  });

  testWidgets('a single-plan catalog renders both Omi Pro intervals with no empty cards', (tester) async {
    // 2026-10-24 ruling: a new buyer's catalog is unlimited_v2 only. The sheet
    // falls back to its single-tier layout — one card per billing interval,
    // a working selection and an Upgrade action, nothing empty or dangling.
    await _pumpPlansSheet(
      tester,
      subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
      plans: [
        _price('unlimited_v2', 'Unlimited Annual', 'year', 26991),
        _price('unlimited_v2', 'Unlimited Monthly', 'month', 2999),
      ],
    );

    expect(
      find.byType(PlanOptionCard),
      findsNWidgets(2),
      reason: 'one card per billing interval of the single tier, no empty tier slots',
    );
    expect(_selected(tester, 'Omi Pro · Yearly'), isTrue, reason: 'yearly stays the default selection');
    expect(find.text('Works on Desktop'), findsNWidgets(2), reason: 'Omi Pro includes the desktop app');

    await _tapVisible(tester, find.widgetWithText(PlanOptionCard, 'Omi Pro · Monthly'));
    expect(_selected(tester, 'Omi Pro · Monthly'), isTrue);
    expect(_selected(tester, 'Omi Pro · Yearly'), isFalse);
    expect(find.byKey(const ValueKey('plans_sheet_upgrade_button')), findsOneWidget);
  });
  testWidgets('JPY annual card uses whole-yen billing total and keeps the selected target', (tester) async {
    final yearly = _price('unlimited_v2', 'Unlimited Annual', 'year', 43200)
      ..addAll({'currency': 'jpy', 'billing_total': '43,200 JPY', 'price_string': '3,600 JPY/mo'});
    final monthly = _price('unlimited_v2', 'Unlimited Monthly', 'month', 4800)
      ..addAll({'currency': 'jpy', 'billing_total': '4,800 JPY', 'price_string': '4,800 JPY/mo'});
    await _pumpPlansSheet(tester,
        subscription:
            Subscription(plan: PlanType.plus, status: SubscriptionStatus.active, stripeSubscriptionId: 'sub_fixture'),
        plans: [yearly, monthly]);
    expect(find.textContaining('43,200 JPY'), findsOneWidget);
    expect(find.textContaining('\$432'), findsNothing);
    expect(_selected(tester, 'Omi Pro · Yearly'), isTrue);
    await _tapVisible(tester, find.widgetWithText(PlanOptionCard, 'Omi Pro · Monthly'));
    expect(_selected(tester, 'Omi Pro · Monthly'), isTrue);
    await _tapVisible(tester, find.byKey(const ValueKey('plans_sheet_upgrade_button')));
    // Continue stays busy while its confirmation is open, so its spinner
    // intentionally keeps scheduling frames. Pump the dialog transition only.
    await tester.pump(const Duration(milliseconds: 400));
    final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));
    expect(find.text(l10n.confirmPlanChange), findsOneWidget,
        reason: 'fresh JPY offer must not require a matching USD ID in the usage catalog');
    expect(find.textContaining('4,800 JPY'), findsWidgets);
  });
}
