import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

const _phone = Size(402, 874);

class _Auth extends AuthenticationProvider {
  _Auth() : super(initializeListeners: false);

  final opened = <String>[];

  @override
  void openTermsOfService() => opened.add('terms');

  @override
  void openPrivacyPolicy() => opened.add('privacy');
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

Future<_Auth> _pump(WidgetTester tester, {Subscription? subscription, double textScale = 1}) async {
  tester.view.physicalSize = _phone * 3;
  tester.view.devicePixelRatio = 3;
  tester.view.padding = const FakeViewPadding(top: 62 * 3, bottom: 34 * 3);
  addTearDown(tester.view.reset);
  final usage = UsageProvider();
  addTearDown(usage.dispose);
  final paid = subscription?.plan.isPaid ?? false;
  usage.debugSetSubscription(UserSubscriptionResponse(
    subscription: subscription ?? Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
    transcriptionSecondsUsed: 0,
    transcriptionSecondsLimit: 0,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
  ));
  usage.debugSetAvailablePlans({
    'plans': <dynamic>[_price('year', 26991), _price('month', 2999, active: paid)],
  });
  final auth = _Auth();
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
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
        home: const Scaffold(body: Align(alignment: Alignment.bottomCenter, child: _Harness())),
      ),
    ),
  );
  await tester.pump();
  return auth;
}

Finder _inList(Finder finder) => find.descendant(of: find.byType(ListView), matching: finder);

void _expectOnScreen(WidgetTester tester, Finder finder, String what) {
  expect(finder, findsOneWidget, reason: what);
  final rect = tester.getRect(finder);
  expect(rect.top, greaterThanOrEqualTo(0), reason: '$what top');
  expect(rect.bottom, lessThanOrEqualTo(_phone.height - 34), reason: '$what bottom, above the home indicator');
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('free plan: the charge, Upgrade and Terms/Privacy show on the first screen, pinned under the list',
      (tester) async {
    final auth = await _pump(tester);
    expect(tester.takeException(), isNull);
    final charge = find.byKey(const ValueKey('plans_sheet_charge_line'));
    final upgrade = find.byKey(const ValueKey('plans_sheet_upgrade_button'));
    final terms = find.byKey(const ValueKey('plans_sheet_terms'));
    final privacy = find.byKey(const ValueKey('plans_sheet_privacy'));
    _expectOnScreen(tester, charge, 'charge line');
    _expectOnScreen(tester, upgrade, 'Upgrade');
    _expectOnScreen(tester, terms, 'Terms of Use');
    _expectOnScreen(tester, privacy, 'Privacy Policy');
    expect(tester.widget<Text>(charge).data, r'US$269.91/year', reason: 'yearly stays the default selection');
    expect(_inList(upgrade), findsNothing, reason: 'pinned outside the scrolling plans');
    expect(tester.getRect(charge).bottom, lessThanOrEqualTo(tester.getRect(upgrade).top));
    expect(tester.getRect(upgrade).bottom, lessThanOrEqualTo(tester.getRect(terms).top));
    for (final link in [terms, privacy]) {
      expect(tester.getRect(link).height, greaterThanOrEqualTo(44), reason: '44pt target');
    }
    expect(find.text('Upgrade'), findsOneWidget, reason: 'one Upgrade, no second one in the list');

    await tester.tap(terms);
    await tester.tap(privacy);
    expect(auth.opened, ['terms', 'privacy']);
  });

  testWidgets('free plan: picking Monthly changes the pinned charge line', (tester) async {
    await _pump(tester);
    final monthly = find.widgetWithText(PlanOptionCard, 'Omi Pro · Monthly');
    await tester.ensureVisible(monthly);
    await tester.pump();
    await tester.tap(monthly);
    await tester.pump();
    expect(tester.widget<Text>(find.byKey(const ValueKey('plans_sheet_charge_line'))).data, r'US$29.99/month');
  });

  testWidgets('free plan at accessibility text: the footer scrolls with the page instead of covering it',
      (tester) async {
    await _pump(tester, textScale: 2);
    expect(tester.takeException(), isNull);
    expect(_inList(find.byKey(const ValueKey('plans_sheet_free_footer'))), findsOneWidget);
    await tester.scrollUntilVisible(find.byKey(const ValueKey('plans_sheet_upgrade_button')), 300);
    expect(find.byKey(const ValueKey('plans_sheet_terms')), findsOneWidget);
  });

  testWidgets('paid plan: no footer, Continue stays in the list', (tester) async {
    await _pump(
      tester,
      subscription: Subscription(
        plan: PlanType.unlimitedV2,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_1',
        currentPriceId: 'price_unlimited_v2_month',
      ),
    );
    expect(find.byKey(const ValueKey('plans_sheet_free_footer')), findsNothing);
    expect(find.byKey(const ValueKey('plans_sheet_terms')), findsNothing);
    expect(_inList(find.byKey(const ValueKey('plans_sheet_upgrade_button'))), findsOneWidget);
    expect(find.text('Continue'), findsOneWidget);
  });
}
