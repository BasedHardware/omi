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
        plan: PlanType.unlimitedV2,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_1',
        currentPriceId: 'price_unlimited_v2_month',
      ),
      plans: [
        _price('plus', 'Plus', 'month', 900),
        _price('plus', 'Plus', 'year', 9000),
        _price('unlimited_v2', 'Unlimited', 'month', 1900, active: true),
        _price('unlimited_v2', 'Unlimited', 'year', 19000),
      ],
    );
    final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));
    final upgradeButton = find.byKey(const ValueKey('plans_sheet_upgrade_button'));

    await _tapVisible(tester, find.widgetWithText(PlanOptionCard, 'Plus'));
    expect(_selected(tester, 'Plus'), isTrue);

    await _tapVisible(tester, find.text(l10n.billingMonthly));
    expect(_selected(tester, 'Plus'), isTrue);
    expect(upgradeButton, findsOneWidget);

    await _tapVisible(tester, find.widgetWithText(PlanOptionCard, 'Unlimited'));
    expect(_selected(tester, 'Unlimited'), isTrue);
    expect(_selected(tester, 'Plus'), isFalse);
    expect(upgradeButton, findsNothing, reason: 'nothing to switch to on the price already paid');

    await _tapVisible(tester, find.text(l10n.billingYearly));
    expect(_selected(tester, 'Unlimited'), isTrue);
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

    await _tapVisible(tester, find.widgetWithText(PlanOptionCard, 'Unlimited'));
    expect(_selected(tester, 'Unlimited'), isTrue);

    await _tapVisible(tester, find.text(l10n.billingMonthly));
    expect(find.widgetWithText(PlanOptionCard, 'Unlimited'), findsNothing);
    expect(_selected(tester, 'Plus'), isTrue, reason: 'the hidden Unlimited card must not stay selected');
  });
}
