import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/yearly_switch.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../support/recording_analytics.dart';

final _now = DateTime.utc(2026, 10, 26, 12);
final int _prorationDate = _now.millisecondsSinceEpoch ~/ 1000;
final int _renewsAt = DateTime.utc(2027, 10, 26, 12).millisecondsSinceEpoch ~/ 1000;

wire.GeneratedYearlySwitchResponse _offer({
  bool eligible = true,
  String reason = 'eligible',
  bool firstBillingPeriod = false,
  bool preview = false,
  int amountDueToday = 24492,
  int? prorationDate,
}) =>
    wire.GeneratedYearlySwitchResponse(
      eligible: eligible,
      reason: reason,
      planId: eligible ? 'unlimited_v2' : null,
      priceId: eligible ? 'price_unlimited_year' : null,
      currency: eligible ? 'usd' : null,
      monthlyAmount: eligible ? 2999 : null,
      yearlyAmount: eligible ? 26991 : null,
      savingsAmount: eligible ? 8997 : null,
      firstBillingPeriod: eligible ? firstBillingPeriod : null,
      amountDueToday: eligible && preview ? amountDueToday : null,
      renewsAt: eligible && preview ? _renewsAt : null,
      prorationDate: eligible && preview ? (prorationDate ?? _prorationDate) : null,
    );

/// Answers like GET /v1/payments/yearly-switch and the plan-change endpoint.
class _Backend {
  _Backend({this.offer, this.previewFailures = 0, this.switchResult = const {'status': 'success'}});

  wire.GeneratedYearlySwitchResponse? offer;
  int previewFailures;
  Map<String, dynamic>? switchResult;
  int amountDueToday = 24492;

  /// What a plain lookup answers after a switch whose response was lost (null: unreadable).
  wire.GeneratedYearlySwitchResponse? Function()? afterSwitch;
  final loads = <bool>[];
  final switches = <(String, int, int)>[];
  int _previews = 0;

  Future<wire.GeneratedYearlySwitchResponse?> load({bool preview = false}) async {
    loads.add(preview);
    final base = offer;
    if (!preview && switches.isNotEmpty && afterSwitch != null) return afterSwitch!();
    if (base == null) return null;
    if (!preview) return base;
    if (previewFailures > 0) {
      previewFailures--;
      return null;
    }
    // Each preview is a new Stripe proration date, one second after the last.
    return _offer(
      eligible: base.eligible,
      reason: base.reason,
      preview: true,
      amountDueToday: amountDueToday,
      prorationDate: _prorationDate + _previews++,
    );
  }

  Future<Map<String, dynamic>?> apply({
    required String priceId,
    required int prorationDate,
    required int expectedAmountDue,
  }) async {
    switches.add((priceId, prorationDate, expectedAmountDue));
    return switchResult;
  }
}

class _Usage extends UsageProvider {
  int fetches = 0;

  @override
  Future<void> fetchSubscription() async => fetches++;

  @override
  Future<void> loadAvailablePlans() async {}
}

/// A monthly subscriber 5 days into the month.
final int _monthlyPeriodEnd = _now.add(const Duration(days: 25)).millisecondsSinceEpoch ~/ 1000;

Future<_Usage> _pump(
  WidgetTester tester,
  Widget child, {
  SubscriptionStatus status = SubscriptionStatus.active,
  int? periodEnd,
}) async {
  tester.view.physicalSize = const Size(430, 932);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final usage = _Usage();
  addTearDown(usage.dispose);
  usage.debugSetSubscription(
    UserSubscriptionResponse(
      subscription: Subscription(
        plan: PlanType.unlimitedV2,
        status: status,
        stripeSubscriptionId: 'sub_monthly',
        currentPriceId: 'price_unlimited_month',
        currentPeriodEnd: periodEnd ?? _monthlyPeriodEnd,
      ),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    ),
  );
  await tester.pumpWidget(
    ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        locale: const Locale('en'),
        home: Scaffold(body: ListView(children: [child])),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return usage;
}

AppLocalizations _l10n(WidgetTester tester) => AppLocalizations.of(tester.element(find.byType(Scaffold).first));

String _renewsLabel(WidgetTester tester) => OmiDateFormat.of(tester.element(find.byType(Scaffold).first))
    .date(DateTime.fromMillisecondsSinceEpoch(_renewsAt * 1000));

void main() {
  late RecordingAnalytics analytics;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    analytics = RecordingAnalytics();
    AnalyticsManager.configure(analytics.adapter);
    await AnalyticsManager.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  group('Plans & Billing row', () {
    testWidgets('a monthly subscriber sees the saving and confirms the exact preview', (tester) async {
      final backend = _Backend(offer: _offer());
      final usage = await _pump(tester, YearlySwitchPlansRow(load: backend.load, apply: backend.apply));
      final l10n = _l10n(tester);

      expect(find.text(l10n.yearlySwitchTitle), findsOneWidget);
      expect(find.text(l10n.yearlySwitchRowSavings('US\$89.97')), findsOneWidget);
      analytics.expectSingle('Subscription Yearly Switch Shown', {'surface': 'plans'});

      await tester.tap(find.byKey(const Key('yearly_switch_plans_row')));
      await tester.pumpAndSettle();

      analytics.expectSingle('Subscription Yearly Switch Opened', {'surface': 'plans'});
      expect(backend.loads, [false, true]);
      expect(find.text(l10n.yearlySwitchPlanValue('Omi Pro', 'US\$269.91')), findsOneWidget);
      expect(find.text('US\$244.92'), findsOneWidget);
      expect(find.text(_renewsLabel(tester)), findsOneWidget);
      expect(find.text(l10n.yearlySwitchCreditNote), findsOneWidget);
      expect(find.byKey(const Key('yearly_switch_cancel')), findsOneWidget);

      await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
      await tester.pumpAndSettle();

      // The switch is charged at the date Stripe previewed, for the amount on screen only.
      expect(backend.switches, [('price_unlimited_year', _prorationDate, 24492)]);
      expect(find.text(l10n.yearlySwitchDoneTitle), findsOneWidget);
      expect(find.text(l10n.yearlySwitchDoneBody('US\$244.92', _renewsLabel(tester))), findsOneWidget);
      expect(usage.fetches, 1);
      analytics.expectSingle('Subscription Yearly Switch Confirmed', {'surface': 'plans'});
      analytics.expectSingle('Subscription Yearly Switch Succeeded', {'surface': 'plans'});

      await tester.tap(find.byKey(const Key('yearly_switch_done_button')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('yearly_switch_plans_row')), findsNothing);
    });

    testWidgets('a declined card keeps the reader on monthly and lets them try again', (tester) async {
      final backend = _Backend(
        offer: _offer(),
        switchResult: {'error': true, 'status_code': 402, 'detail': 'Your card was declined.'},
      );
      final usage = await _pump(tester, YearlySwitchPlansRow(load: backend.load, apply: backend.apply));
      final l10n = _l10n(tester);

      await tester.tap(find.byKey(const Key('yearly_switch_plans_row')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
      await tester.pumpAndSettle();

      expect(find.text(l10n.yearlySwitchDeclined), findsOneWidget);
      expect(find.text(l10n.yearlySwitchDoneTitle), findsNothing);
      expect(usage.fetches, 0);
      analytics.expectSingle('Subscription Yearly Switch Failed', {'surface': 'plans', 'reason': 'declined'});

      // A second try re-previews first (a fresh proration date and idempotency key), same amount: it goes through.
      backend.switchResult = {'status': 'success'};
      await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
      await tester.pumpAndSettle();
      expect(backend.loads, [false, true, true]);
      expect(backend.switches, [
        ('price_unlimited_year', _prorationDate, 24492),
        ('price_unlimited_year', _prorationDate + 1, 24492),
      ]);
      expect(find.text(l10n.yearlySwitchDoneTitle), findsOneWidget);
    });

    testWidgets('a retry whose amount moved shows the new amount and charges nothing until confirmed', (tester) async {
      final backend = _Backend(offer: _offer(), switchResult: {'error': true, 'status_code': 409});
      await _pump(tester, YearlySwitchPlansRow(load: backend.load, apply: backend.apply));
      await tester.tap(find.byKey(const Key('yearly_switch_plans_row')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
      await tester.pumpAndSettle();
      expect(backend.switches, hasLength(1));

      backend.amountDueToday = 24312;
      backend.switchResult = {'status': 'success'};
      await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
      await tester.pumpAndSettle();
      expect(find.text('US\$243.12'), findsOneWidget);
      expect(find.text('US\$244.92'), findsNothing);
      expect(backend.switches, hasLength(1));

      await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
      await tester.pumpAndSettle();
      expect(backend.switches.last, ('price_unlimited_year', _prorationDate + 1, 24312));
      expect(find.text(_l10n(tester).yearlySwitchDoneTitle), findsOneWidget);
    });

    testWidgets('a lost response is settled by reading Stripe again, never guessed', (tester) async {
      final backend = _Backend(offer: _offer(), switchResult: null)
        ..afterSwitch = () => _offer(eligible: false, reason: 'not_monthly');
      final usage = await _pump(tester, YearlySwitchPlansRow(load: backend.load, apply: backend.apply));
      await tester.tap(find.byKey(const Key('yearly_switch_plans_row')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
      await tester.pumpAndSettle();
      // The switch landed even though its response was lost: the reader sees it, not an error.
      expect(find.text(_l10n(tester).yearlySwitchDoneTitle), findsOneWidget);
      expect(usage.fetches, 1);
      analytics.expectSingle('Subscription Yearly Switch Succeeded', {'surface': 'plans'});
    });

    testWidgets('an unreadable outcome does not claim the reader is still monthly', (tester) async {
      final backend = _Backend(offer: _offer(), switchResult: null)..afterSwitch = () => null;
      await _pump(tester, YearlySwitchPlansRow(load: backend.load, apply: backend.apply));
      final l10n = _l10n(tester);
      await tester.tap(find.byKey(const Key('yearly_switch_plans_row')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
      await tester.pumpAndSettle();
      expect(find.text(l10n.somethingWentWrong), findsOneWidget);
      expect(find.text(l10n.yearlySwitchFailed), findsNothing);
      expect(find.text(l10n.yearlySwitchDoneTitle), findsNothing);
    });

    testWidgets('a refused or failed switch says nothing changed', (tester) async {
      final backend = _Backend(offer: _offer(), switchResult: {'error': true, 'status_code': 409});
      await _pump(tester, YearlySwitchPlansRow(load: backend.load, apply: backend.apply));
      final l10n = _l10n(tester);
      await tester.tap(find.byKey(const Key('yearly_switch_plans_row')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
      await tester.pumpAndSettle();
      expect(find.text(l10n.yearlySwitchFailed), findsOneWidget);
      analytics.expectSingle('Subscription Yearly Switch Failed', {'surface': 'plans', 'reason': 'refused'});

      backend.switchResult = null;
      await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
      await tester.pumpAndSettle();
      expect(find.text(l10n.yearlySwitchFailed), findsOneWidget);
      expect(analytics.propertiesOf('Subscription Yearly Switch Failed').last['reason'], 'error');
    });

    testWidgets('a preview that fails to load offers Try Again instead of a guess', (tester) async {
      final backend = _Backend(offer: _offer(), previewFailures: 1);
      await _pump(tester, YearlySwitchPlansRow(load: backend.load, apply: backend.apply));
      final l10n = _l10n(tester);

      await tester.tap(find.byKey(const Key('yearly_switch_plans_row')));
      await tester.pumpAndSettle();
      expect(find.text(l10n.yearlySwitchPreviewFailed), findsOneWidget);
      expect(find.byKey(const Key('yearly_switch_confirm')), findsNothing);
      analytics
          .expectSingle('Subscription Yearly Switch Failed', {'surface': 'plans', 'reason': 'preview_unavailable'});

      await tester.tap(find.text(l10n.tryAgain));
      await tester.pumpAndSettle();
      expect(find.text('US\$244.92'), findsOneWidget);
      expect(find.byKey(const Key('yearly_switch_confirm')), findsOneWidget);
    });

    testWidgets('an ineligible subscription (trial, discount, past due) gets no row', (tester) async {
      final backend = _Backend(offer: _offer(eligible: false, reason: 'discounted'));
      await _pump(tester, YearlySwitchPlansRow(load: backend.load, apply: backend.apply));
      expect(find.byKey(const Key('yearly_switch_plans_row')), findsNothing);
      expect(analytics.names, isNot(contains('Subscription Yearly Switch Shown')));
    });

    testWidgets('an inactive subscription is never asked', (tester) async {
      final backend = _Backend(offer: _offer());
      await _pump(
        tester,
        YearlySwitchPlansRow(load: backend.load, apply: backend.apply),
        status: SubscriptionStatus.inactive,
      );
      expect(backend.loads, isEmpty);
      expect(find.byKey(const Key('yearly_switch_plans_row')), findsNothing);
    });
  });

  group('Home row', () {
    testWidgets('past the first paid month it shows once, then stays quiet for 30 days', (tester) async {
      final backend = _Backend(offer: _offer());
      await _pump(tester, YearlySwitchHomeRow(load: backend.load, apply: backend.apply, now: () => _now));
      final l10n = _l10n(tester);

      // The exact saving, never rounded up.
      expect(find.text(l10n.yearlySwitchHomeTitle('US\$89.97')), findsOneWidget);
      expect(find.text(l10n.yearlySwitchHomeSubtitle), findsOneWidget);
      analytics.expectSingle('Subscription Yearly Switch Shown', {'surface': 'home'});
      expect(SharedPreferencesUtil().yearlySwitchHomeShownAt, _now.millisecondsSinceEpoch);

      // The next launch inside 30 days: no row, and the backend is not even asked.
      backend.loads.clear();
      await _pump(
        tester,
        YearlySwitchHomeRow(
          key: UniqueKey(),
          load: backend.load,
          apply: backend.apply,
          now: () => _now.add(const Duration(days: 29)),
        ),
      );
      expect(find.byKey(const Key('yearly_switch_home_row')), findsNothing);
      expect(backend.loads, isEmpty);

      await _pump(
        tester,
        YearlySwitchHomeRow(
          key: UniqueKey(),
          load: backend.load,
          apply: backend.apply,
          now: () => _now.add(const Duration(days: 31)),
        ),
      );
      expect(find.byKey(const Key('yearly_switch_home_row')), findsOneWidget);
    });

    testWidgets('a subscription that loads after Home mounts still gets the row', (tester) async {
      final backend = _Backend(offer: _offer());
      final usage = await _pump(tester, YearlySwitchHomeRow(load: backend.load, apply: backend.apply, now: () => _now));
      final loaded = usage.subscription;
      // Cold start: Home renders before /v1/users/me/subscription answers.
      usage.debugSetSubscription(null);
      await tester.pumpWidget(
        ChangeNotifierProvider<UsageProvider>.value(
          value: usage,
          child: MaterialApp(
            theme: buildOmiTheme(),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            locale: const Locale('en'),
            home: Scaffold(
              body: ListView(
                children: [
                  YearlySwitchHomeRow(key: UniqueKey(), load: backend.load, apply: backend.apply, now: () => _now),
                ],
              ),
            ),
          ),
        ),
      );
      SharedPreferencesUtil().yearlySwitchHomeShownAt = 0;
      backend.loads.clear();
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('yearly_switch_home_row')), findsNothing);
      expect(backend.loads, isEmpty);

      usage.debugSetSubscription(loaded);
      await tester.pumpAndSettle();
      expect(backend.loads, [false]);
      expect(find.byKey(const Key('yearly_switch_home_row')), findsOneWidget);
    });

    testWidgets('a Home without the usage provider renders nothing and asks nothing', (tester) async {
      final backend = _Backend(offer: _offer());
      await tester.pumpWidget(
        MaterialApp(
          theme: buildOmiTheme(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: YearlySwitchHomeRow(load: backend.load, apply: backend.apply, now: () => _now)),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('yearly_switch_home_row')), findsNothing);
      expect(backend.loads, isEmpty);
    });

    testWidgets('a yearly subscriber is never looked up', (tester) async {
      final backend = _Backend(offer: _offer(eligible: false, reason: 'not_monthly'));
      await _pump(
        tester,
        YearlySwitchHomeRow(load: backend.load, apply: backend.apply, now: () => _now),
        periodEnd: _renewsAt,
      );
      expect(backend.loads, isEmpty);
      expect(find.byKey(const Key('yearly_switch_home_row')), findsNothing);
    });

    testWidgets('the first paid month gets no Home row', (tester) async {
      final backend = _Backend(offer: _offer(firstBillingPeriod: true));
      await _pump(tester, YearlySwitchHomeRow(load: backend.load, apply: backend.apply, now: () => _now));
      expect(find.byKey(const Key('yearly_switch_home_row')), findsNothing);
      expect(SharedPreferencesUtil().yearlySwitchHomeShownAt, 0);
    });

    testWidgets('dismiss hides the row; tapping it opens the same confirm sheet', (tester) async {
      final backend = _Backend(offer: _offer());
      await _pump(tester, YearlySwitchHomeRow(load: backend.load, apply: backend.apply, now: () => _now));
      final l10n = _l10n(tester);

      await tester.tap(find.byKey(const Key('yearly_switch_home_row')));
      await tester.pumpAndSettle();
      expect(find.text(l10n.yearlySwitchDueToday), findsOneWidget);
      analytics.expectSingle('Subscription Yearly Switch Opened', {'surface': 'home'});
      await tester.tap(find.byKey(const Key('yearly_switch_cancel')));
      await tester.pumpAndSettle();
      expect(backend.switches, isEmpty);

      await tester.tap(find.byKey(const Key('yearly_switch_dismiss')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('yearly_switch_home_row')), findsNothing);
      analytics.expectSingle('Subscription Yearly Switch Dismissed', {'surface': 'home'});
    });
  });
}
