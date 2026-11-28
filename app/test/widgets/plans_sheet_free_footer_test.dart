import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';
import 'package:omi/pages/settings/widgets/plans/prepaid_code_sheet.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/plan_pricing.dart';
import 'package:omi/utils/platform/platform_manager.dart';

const _phone = Size(402, 874);
const _compact = Size(375, 667);
const _tight = Size(360, 560);

class _Auth extends AuthenticationProvider {
  _Auth() : super(initializeListeners: false);

  final opened = <String>[];

  @override
  void openTermsOfService() => opened.add('terms');

  @override
  void openPrivacyPolicy() => opened.add('privacy');
}

/// Records each checkout request; [hold] keeps it pending until the test completes it.
class _Usage extends UsageProvider {
  final requests = <(String, String?)>[];
  Completer<Map<String, dynamic>?>? hold;

  /// The plans reload Checkout's return starts: the cards show their loading placeholder.
  bool loading = false;

  @override
  bool get isLoadingPlans => loading;

  @override
  Future<void> loadAvailablePlans() async {}

  @override
  Future<void> fetchSubscription({bool fresh = false}) async {}

  @override
  Future<Map<String, dynamic>?> createUserCheckoutSession({
    required String priceId,
    String? promotionCode,
    int? trialDays,
  }) {
    requests.add((priceId, promotionCode));
    return hold?.future ?? Future.value(null);
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
  Widget build(BuildContext context) => PlansSheet(
        waveController: _animation,
        notesController: _animation,
        arrowController: _animation,
        arrowAnimation: _animation,
        readStorefrontGate: () async => false,
      );
}

Map<String, dynamic> _price(String interval, int amount, {bool active = false}) => {
      'id': 'price_unlimited_v2_$interval',
      'plan_id': 'unlimited_v2',
      'title': interval == 'year' ? 'Unlimited Annual' : 'Unlimited Monthly',
      'interval': interval,
      'unit_amount': amount,
      'price_string': interval == 'year' ? r'$269.91/yr' : r'$29.99/mo',
      'is_active': active,
    };

late _Usage _usage;

Future<_Auth> _pump(
  WidgetTester tester, {
  Subscription? subscription,
  PaymentIssue? paymentIssue,
  List<Map<String, dynamic>>? plans,
  double textScale = 1,
  Size size = _phone,
  bool inSheet = false,
  double keyboard = 0,
  bool prepaidCodeRedeem = false,
}) async {
  tester.view.physicalSize = size * 3;
  tester.view.devicePixelRatio = 3;
  tester.view.padding = const FakeViewPadding(top: 62 * 3, bottom: 34 * 3);
  if (keyboard > 0) tester.view.viewInsets = FakeViewPadding(bottom: keyboard * 3);
  addTearDown(tester.view.reset);
  _usage = _Usage();
  addTearDown(_usage.dispose);
  final paid = subscription?.plan.isPaid ?? false;
  _usage.debugSetSubscription(UserSubscriptionResponse(
    subscription: subscription ?? Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
    transcriptionSecondsUsed: 0,
    transcriptionSecondsLimit: 0,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
    paymentIssue: paymentIssue,
    prepaidCodeRedeem: prepaidCodeRedeem,
  ));
  _usage.debugSetAvailablePlans({
    'plans': <dynamic>[
      ...plans ?? [_price('year', 26991), _price('month', 2999, active: paid)]
    ],
  });
  final auth = _Auth();
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<UsageProvider>.value(value: _usage),
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ChangeNotifierProvider<AuthenticationProvider>.value(value: auth),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
          child: child!,
        ),
        home: inSheet
            // The real shell: title row, keyboard padding, route constraints.
            ? Scaffold(
                body: Builder(
                  builder: (context) => Center(
                    child: TextButton(
                      onPressed: () => showOmiSheet<void>(
                        context: context,
                        title: 'Plans & Billing',
                        padding: EdgeInsets.zero,
                        builder: (_) => const _Harness(),
                      ),
                      child: const Text('open'),
                    ),
                  ),
                ),
              )
            : const Scaffold(body: Align(alignment: Alignment.bottomCenter, child: _Harness())),
      ),
    ),
  );
  await tester.pump();
  if (inSheet) {
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
  }
  await tester.pump();
  return auth;
}

Finder _inList(Finder finder) => find.descendant(of: find.byType(ListView), matching: finder);

const _footer = ValueKey('plans_sheet_free_footer');
const _charge = ValueKey('plans_sheet_charge_line');
const _upgrade = ValueKey('plans_sheet_upgrade_button');

String _chargeText(WidgetTester tester) => tester.widget<Text>(find.byKey(_charge)).data!;

void _expectOnScreen(WidgetTester tester, Finder finder, String what, {Size size = _phone, double bottomInset = 34}) {
  expect(finder, findsOneWidget, reason: what);
  final rect = tester.getRect(finder);
  expect(rect.top, greaterThanOrEqualTo(0), reason: '$what top');
  expect(rect.bottom, lessThanOrEqualTo(size.height - bottomInset), reason: '$what bottom, above the inset');
}

double _contrast(Color a, Color b) {
  final la = a.computeLuminance(), lb = b.computeLuminance();
  return (la > lb ? la + 0.05 : lb + 0.05) / (la > lb ? lb + 0.05 : la + 0.05);
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('free plan: the charge, Upgrade, renewal terms and Terms/Privacy show on the first screen, pinned',
      (tester) async {
    final auth = await _pump(tester);
    expect(tester.takeException(), isNull);
    final charge = find.byKey(_charge);
    final upgrade = find.byKey(_upgrade);
    final renewal = find.byKey(const ValueKey('plans_sheet_renewal_terms'));
    final terms = find.byKey(const ValueKey('plans_sheet_terms'));
    final privacy = find.byKey(const ValueKey('plans_sheet_privacy'));
    _expectOnScreen(tester, charge, 'charge line');
    _expectOnScreen(tester, upgrade, 'Upgrade');
    _expectOnScreen(tester, renewal, 'renewal terms');
    _expectOnScreen(tester, terms, 'Terms of Use');
    _expectOnScreen(tester, privacy, 'Privacy Policy');
    expect(_chargeText(tester), r'US$269.91/year', reason: 'yearly stays the default selection');
    expect(tester.widget<Text>(renewal).data,
        r'Omi Pro renews automatically at US$269.91/year until you cancel in Settings > Plan & Usage.');
    expect(_inList(upgrade), findsNothing, reason: 'pinned outside the scrolling plans');
    expect(tester.getRect(charge).bottom, lessThanOrEqualTo(tester.getRect(upgrade).top));
    expect(tester.getRect(upgrade).bottom, lessThanOrEqualTo(tester.getRect(renewal).top));
    expect(tester.getRect(renewal).bottom, lessThanOrEqualTo(tester.getRect(terms).top));
    for (final link in [terms, privacy]) {
      expect(tester.getRect(link).height, greaterThanOrEqualTo(44), reason: '44pt target');
    }
    expect(find.text('Upgrade'), findsOneWidget, reason: 'one Upgrade, no second one in the list');

    await tester.tap(terms);
    await tester.tap(privacy);
    expect(auth.opened, ['terms', 'privacy']);
  });

  testWidgets('free plan: the pinned charge and the submitted price are the checkout resolver\'s offer',
      (tester) async {
    await _pump(tester);
    final plans = (_usage.availablePlans!['plans'] as List).cast<Map<String, dynamic>>();
    for (final (card, interval) in [('Omi Pro · Monthly', 'month'), ('Omi Pro · Yearly', 'year')]) {
      final option = find.widgetWithText(PlanOptionCard, card);
      await tester.ensureVisible(option);
      await tester.pump();
      await tester.tap(option);
      await tester.pump();
      final offer = planForCheckout(plans, interval: interval, selectedTierId: 'unlimited_v2')!;
      final l10n = AppLocalizations.of(tester.element(find.byKey(_charge)));
      expect(_chargeText(tester), l10n.billingRecurringPrice(planBillingTotal(offer), interval));
      await tester.tap(find.byKey(_upgrade));
      await tester.pump();
      expect(_usage.requests.last.$1, offer['id'], reason: 'Upgrade submits the offer the footer shows');
    }
  });

  testWidgets('free plan with a monthly-only catalog: one Monthly card, its charge and Upgrade', (tester) async {
    await _pump(tester, plans: [_price('month', 2999)]);
    expect(find.widgetWithText(PlanOptionCard, 'Omi Pro · Yearly'), findsNothing, reason: 'no offer, no card');
    expect(find.widgetWithText(PlanOptionCard, 'Omi Pro · Monthly'), findsOneWidget);
    expect(_chargeText(tester), r'US$29.99/month');
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests.single.$1, 'price_unlimited_v2_month');
  });

  testWidgets('free plan with an empty catalog: no charge and no Upgrade, the retry state instead', (tester) async {
    await _pump(tester, plans: []);
    expect(tester.takeException(), isNull);
    expect(find.byKey(_upgrade), findsNothing);
    expect(find.byKey(_charge), findsNothing);
    expect(find.byType(OmiErrorState), findsOneWidget);
  });

  testWidgets('free plan with a promo code: the amount is labelled before discounts', (tester) async {
    await _pump(tester);
    await tester.ensureVisible(find.text('Promo code'));
    await tester.pump();
    await tester.tap(find.text('Promo code'));
    await tester.pump();
    await tester.enterText(find.byKey(const ValueKey('plans_sheet_promo_code')), 'SAVE50');
    await tester.pump();
    expect(_chargeText(tester), r'US$269.91/year before discounts');
    expect(
        tester.widget<Text>(find.byKey(const ValueKey('plans_sheet_renewal_terms'))).data,
        r'Omi Pro renews automatically at the standard price of US$269.91/year before discounts until you cancel in '
        'Settings > Plan & Usage. Checkout shows what you pay now and at renewal.',
        reason: 'a code can change the renewal charges too');
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests.single, ('price_unlimited_v2_year', 'SAVE50'));
  });

  testWidgets('free plan: a code set without a keystroke still labels the amount before discounts', (tester) async {
    await _pump(tester);
    await tester.ensureVisible(find.text('Promo code'));
    await tester.pump();
    await tester.tap(find.text('Promo code'));
    await tester.pump();
    tester.widget<TextField>(find.byKey(const ValueKey('plans_sheet_promo_code'))).controller!.text = 'SAVE50';
    await tester.pump();
    expect(_chargeText(tester), r'US$269.91/year before discounts');
  });

  testWidgets('free plan: plan and promo stay locked while checkout is pending, and unlock after a refusal',
      (tester) async {
    await _pump(tester);
    await tester.ensureVisible(find.text('Promo code'));
    await tester.pump();
    await tester.tap(find.text('Promo code'));
    await tester.pump();
    final promo = find.byKey(const ValueKey('plans_sheet_promo_code'));
    await tester.enterText(promo, 'SAVE50');
    await tester.pump();
    _usage.hold = Completer();
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests.single, ('price_unlimited_v2_year', 'SAVE50'));

    final monthly = find.widgetWithText(PlanOptionCard, 'Omi Pro · Monthly');
    await tester.ensureVisible(monthly);
    await tester.pump();
    await tester.tap(monthly, warnIfMissed: false);
    await tester.pump();
    expect(_chargeText(tester), r'US$269.91/year before discounts', reason: 'the footer matches the submitted price');
    expect(tester.widget<PlanOptionCard>(find.widgetWithText(PlanOptionCard, 'Omi Pro · Yearly')).isSelected, isTrue);
    expect(tester.widget<TextField>(promo).enabled, isFalse, reason: 'the submitted code cannot change');

    _usage.hold!.complete({'error': true, 'detail': 'Your card was declined.'});
    await tester.pump();
    await tester.pump();
    expect(find.byKey(const ValueKey('plans_sheet_purchase_error')), findsOneWidget, reason: 'the error stays');
    expect(promo, findsOneWidget, reason: 'the promo field stays open with its code');
    expect(tester.widget<TextField>(promo).enabled, isTrue);
    await tester.tap(monthly);
    await tester.pump();
    expect(_chargeText(tester), r'US$29.99/month before discounts', reason: 'selection works again after a refusal');
  });

  testWidgets('free plan: a plan tap not yet painted refuses Upgrade, then the shown offer is submitted',
      (tester) async {
    await _pump(tester);
    final monthly = find.widgetWithText(PlanOptionCard, 'Omi Pro · Monthly');
    await tester.ensureVisible(monthly);
    await tester.pumpAndSettle();
    expect(_chargeText(tester), r'US$269.91/year');
    // Both taps land before the next frame: Upgrade still shows the yearly price.
    await tester.tap(monthly);
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests, isEmpty, reason: 'never a different price from the one on screen');
    expect(find.text('The price changed. Check it and try again.'), findsWidgets);
    expect(_chargeText(tester), r'US$29.99/month', reason: 'the repaint shows the new offer');
    _usage.hold = Completer();
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests.single, ('price_unlimited_v2_month', null));
    expect(find.byKey(const ValueKey('plans_sheet_purchase_error')), findsNothing, reason: 'the retry starts clean');
    _usage.hold!.complete(null);
    await tester.pumpAndSettle();
  });

  testWidgets('free plan: a catalog refresh not yet painted refuses Upgrade, then the new price is submitted',
      (tester) async {
    await _pump(tester);
    expect(_chargeText(tester), r'US$269.91/year');
    _usage.debugSetAvailablePlans({
      'plans': <dynamic>[
        {..._price('year', 39991), 'id': 'price_unlimited_v2_year_new'},
        _price('month', 2999),
      ],
    });
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests, isEmpty);
    expect(_chargeText(tester), r'US$399.91/year');
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests.single, ('price_unlimited_v2_year_new', null));
  });

  testWidgets('free plan: a code typed but not yet painted refuses Upgrade, then goes with the disclosure',
      (tester) async {
    await _pump(tester);
    await tester.ensureVisible(find.text('Promo code'));
    await tester.pump();
    await tester.tap(find.text('Promo code'));
    await tester.pumpAndSettle();
    tester.widget<TextField>(find.byKey(const ValueKey('plans_sheet_promo_code'))).controller!.value =
        const TextEditingValue(text: 'SAVE50');
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests, isEmpty);
    expect(_chargeText(tester), r'US$269.91/year before discounts');
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests.single, ('price_unlimited_v2_year', 'SAVE50'));
  });

  testWidgets('free plan: "Have a code?" and its discount handoff are locked while checkout is pending',
      (tester) async {
    await _pump(tester, prepaidCodeRedeem: true);
    final entry = find.byKey(const ValueKey('prepaid_code_entry'));
    expect(entry, findsOneWidget);
    _usage.hold = Completer();
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests.single, ('price_unlimited_v2_year', null));

    await tester.ensureVisible(entry);
    await tester.pump();
    await tester.tap(entry, warnIfMissed: false);
    await tester.pump(const Duration(milliseconds: 600)); // the busy Upgrade spins: no settle
    expect(find.byType(PrepaidCodeSheet), findsNothing, reason: 'the code sheet does not open');
    tester.widget<PrepaidCodeEntry>(find.byType(PrepaidCodeEntry)).onDiscountCode!('SAVE50');
    await tester.pump();
    expect(_chargeText(tester), r'US$269.91/year', reason: 'the disclosure stays the one that was submitted');
    expect(find.byKey(const ValueKey('plans_sheet_promo_code')), findsNothing);

    _usage.hold!.complete({'error': true, 'detail': 'Your card was declined.'});
    await tester.pumpAndSettle();
    await tester.tap(entry);
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.byType(PrepaidCodeSheet), findsOneWidget, reason: 'open again once checkout returns');
  });

  testWidgets('not a confirmed free account: a pending checkout locks nothing new, a partial catalog shows as on main',
      (tester) async {
    await _pump(
      tester,
      subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active, stripeSubscriptionId: 's'),
      paymentIssue: const PaymentIssue(status: 'past_due', plan: PlanType.unlimitedV2),
      plans: [_price('month', 2999)],
    );
    expect(tester.takeException(), isNull);
    expect(find.byType(PlanOptionCard), findsNWidgets(2), reason: 'both legacy cards, as on main');
    expect(find.byType(PlanBillingPeriodToggle), findsNothing);

    await _pump(
      tester,
      subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active, stripeSubscriptionId: 's'),
      paymentIssue: const PaymentIssue(status: 'past_due', plan: PlanType.unlimitedV2),
    );
    await tester.ensureVisible(find.text('Promo code'));
    await tester.pump();
    await tester.tap(find.text('Promo code'));
    await tester.pump();
    _usage.hold = Completer();
    await tester.ensureVisible(find.byKey(_upgrade));
    await tester.pump();
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests, hasLength(1));
    expect(tester.widget<TextField>(find.byKey(const ValueKey('plans_sheet_promo_code'))).enabled, isTrue,
        reason: 'the promo field behaves as on main');
    _usage.hold!.complete(null);
    await tester.pumpAndSettle();
  });

  testWidgets('free plan opened in a tight sheet with the keyboard already up: no overflow on the first frame',
      (tester) async {
    await _pump(tester, size: _tight, inSheet: true, keyboard: 310);
    expect(tester.takeException(), isNull, reason: 'the footer scrolls instead of overflowing');
    expect(find.byKey(_upgrade), findsNothing, reason: 'not pinned over the few points left above the keyboard');
    await tester.scrollUntilVisible(find.byKey(_upgrade), 100);
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(_inList(find.byKey(_footer)), findsOneWidget, reason: 'the footer scrolls with the page');
    _expectOnScreen(tester, find.byKey(_upgrade), 'Upgrade', size: _tight, bottomInset: 310);
  });

  testWidgets('free plan: back from Checkout with the keyboard closing and plans reloading keeps the code editable',
      (tester) async {
    await _pump(tester, size: _compact, inSheet: true);
    await tester.ensureVisible(find.text('Promo code'));
    await tester.pump();
    await tester.tap(find.text('Promo code'));
    await tester.pump();
    final promo = find.byKey(const ValueKey('plans_sheet_promo_code'));
    await tester.ensureVisible(promo);
    await tester.pump();
    await tester.tap(promo);
    tester.view.viewInsets = const FakeViewPadding(bottom: 330 * 3);
    await tester.pumpAndSettle();
    await tester.enterText(promo, 'SAVE50');
    await tester.pumpAndSettle();
    expect(_inList(find.byKey(_footer)), findsOneWidget, reason: 'keyboard up: the footer is in the list');

    // Checkout's return: the keyboard is gone and the sheet reloads its plans, in the same frame.
    tester.view.resetViewInsets();
    _usage.loading = true;
    _usage.notifyListeners();
    await tester.pumpAndSettle();
    expect(_inList(find.byKey(_footer)), findsNothing, reason: 'pinned again');
    expect(promo, findsOneWidget, reason: 'the promo field stays open with its code');
    expect(find.text('SAVE50'), findsOneWidget);
    _usage.loading = false;
    _usage.notifyListeners();
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(promo).enabled, isTrue);
    await tester.ensureVisible(find.byTooltip('Clear'));
    await tester.pump();
    await tester.tap(find.byTooltip('Clear'));
    await tester.pump();
    expect(_chargeText(tester), r'US$269.91/year', reason: 'cleared before the retry');
  });

  testWidgets('free plan at accessibility text: the footer scrolls with the page and both links can be tapped',
      (tester) async {
    final auth = await _pump(tester, textScale: 2);
    expect(tester.takeException(), isNull);
    expect(_inList(find.byKey(_footer)), findsOneWidget);
    final terms = find.byKey(const ValueKey('plans_sheet_terms'));
    final privacy = find.byKey(const ValueKey('plans_sheet_privacy'));
    await tester.scrollUntilVisible(terms, 200);
    await tester.pump();
    _expectOnScreen(tester, terms, 'Terms of Use');
    await tester.tap(terms);
    await tester.scrollUntilVisible(privacy, 200);
    await tester.pump();
    _expectOnScreen(tester, privacy, 'Privacy Policy');
    await tester.tap(privacy);
    expect(auth.opened, ['terms', 'privacy']);
  });

  testWidgets('free plan in the real sheet with the keyboard up: the footer scrolls and the promo field stays usable',
      (tester) async {
    await _pump(tester, size: _compact, inSheet: true);
    expect(_inList(find.byKey(_footer)), findsNothing, reason: 'pinned without the keyboard');
    await tester.ensureVisible(find.text('Promo code'));
    await tester.pump();
    await tester.tap(find.text('Promo code'));
    await tester.pump();
    final promo = find.byKey(const ValueKey('plans_sheet_promo_code'));
    await tester.ensureVisible(promo);
    await tester.pump();
    await tester.tap(promo);
    tester.view.viewInsets = const FakeViewPadding(bottom: 330 * 3);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(_inList(find.byKey(_footer)), findsOneWidget, reason: 'too little room: the footer joins the list');
    expect(tester.testTextInput.isVisible, isTrue, reason: 'the field keeps focus while the footer moves');
    await tester.enterText(promo, 'SAVE50');
    await tester.ensureVisible(promo);
    await tester.pumpAndSettle();
    _expectOnScreen(tester, promo, 'promo field', size: _compact, bottomInset: 330);
    expect(find.text('SAVE50'), findsOneWidget);

    tester.view.resetViewInsets();
    await tester.pumpAndSettle();
    expect(promo, findsOneWidget, reason: 'closing the keyboard keeps the promo field open');
    expect(_chargeText(tester), r'US$269.91/year before discounts');
    await tester.ensureVisible(find.byKey(_upgrade));
    await tester.pump();
    await tester.tap(find.byKey(_upgrade));
    await tester.pump();
    expect(_usage.requests.single, ('price_unlimited_v2_year', 'SAVE50'));
  });

  testWidgets('Terms and Privacy pass 4.5:1 on the sheet in light and dark', (tester) async {
    addTearDown(() => OmiColors.active = OmiPalette.light);
    for (final palette in [OmiPalette.light, OmiPalette.dark]) {
      OmiColors.active = palette;
      await _pump(tester);
      final text = find.descendant(of: find.byKey(const ValueKey('plans_sheet_terms')), matching: find.byType(Text));
      final color = tester.widget<Text>(text).style!.color!;
      expect(_contrast(color, palette.surface1), greaterThanOrEqualTo(4.5), reason: '$palette');
    }
  });

  final notFree = <String, (Subscription, PaymentIssue?)>{
    'paid': (
      Subscription(
        plan: PlanType.unlimitedV2,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_1',
        currentPriceId: 'price_unlimited_v2_month',
      ),
      null
    ),
    'trialing (Stripe trial reads as active paid)': (
      Subscription(
        plan: PlanType.unlimitedV2,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_trial',
        currentPriceId: 'price_unlimited_v2_year',
      ),
      null
    ),
    'past due': (
      Subscription(plan: PlanType.basic, status: SubscriptionStatus.active, stripeSubscriptionId: 'sub_due'),
      const PaymentIssue(status: 'past_due', plan: PlanType.unlimitedV2)
    ),
    'unpaid, older response without payment_issue': (
      Subscription(plan: PlanType.basic, status: SubscriptionStatus.active, stripeSubscriptionId: 'sub_unpaid'),
      null
    ),
    'scheduled cancel': (
      Subscription(
        plan: PlanType.basic,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_2',
        cancelAtPeriodEnd: true,
      ),
      null
    ),
    'prepaid': (
      Subscription(
        plan: PlanType.unlimitedV2,
        status: SubscriptionStatus.active,
        prepaid: true,
        currentPeriodEnd: DateTime.now().add(const Duration(days: 30)).millisecondsSinceEpoch ~/ 1000,
      ),
      null
    ),
  };
  for (final MapEntry(key: name, value: (subscription, issue)) in notFree.entries) {
    testWidgets('$name: no new footer, the existing sheet stays', (tester) async {
      await _pump(tester, subscription: subscription, paymentIssue: issue);
      expect(tester.takeException(), isNull);
      expect(find.byKey(_footer), findsNothing);
      expect(find.byKey(_charge), findsNothing);
      expect(find.byKey(const ValueKey('plans_sheet_terms')), findsNothing);
      expect(find.byKey(const ValueKey('plans_sheet_renewal_terms')), findsNothing);
      if (subscription.stripeSubscriptionId != null) {
        expect(find.text('Manage Payment Method'), findsOneWidget, reason: 'recovery path unchanged');
      }
    });
  }

  testWidgets('past due: the existing in-list Upgrade, not the pinned one', (tester) async {
    await _pump(
      tester,
      subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active, stripeSubscriptionId: 's'),
      paymentIssue: const PaymentIssue(status: 'past_due', plan: PlanType.unlimitedV2),
    );
    expect(_inList(find.byKey(_upgrade)), findsOneWidget);
  });

  testWidgets('paid plan: Continue stays in the list', (tester) async {
    await _pump(
      tester,
      subscription: Subscription(
        plan: PlanType.unlimitedV2,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_1',
        currentPriceId: 'price_unlimited_v2_month',
      ),
    );
    expect(_inList(find.byKey(_upgrade)), findsOneWidget);
    expect(find.text('Continue'), findsOneWidget);
  });
}
