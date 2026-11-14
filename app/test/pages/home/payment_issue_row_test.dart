import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/home/widgets/monthly_switch_sheet.dart';
import 'package:omi/pages/home/widgets/payment_issue_row.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../../spine/c7_registry_test.dart' show RecordingAdapter;

UserSubscriptionResponse _response({
  PlanType plan = PlanType.basic,
  PaymentIssue? issue,
  bool showSubscriptionUi = true,
}) =>
    UserSubscriptionResponse(
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      showSubscriptionUi: showSubscriptionUi,
      paymentIssue: issue,
    );

const _pastDue = PaymentIssue(status: 'past_due', plan: PlanType.unlimitedV2);
const _yearlyPastDue = PaymentIssue(
  status: 'past_due',
  plan: PlanType.unlimitedV2,
  monthlySwitch: MonthlySwitchOffer(
    priceId: 'price_1TuIa81F8wnoWYvw0iX0j5M8',
    amount: 2999,
    currency: 'usd',
    yearlyAmount: 26991,
  ),
);

/// The backend answer and the portal are fakes; the row, its opener and the refresh are real.
class _FakeUsage extends UsageProvider {
  _FakeUsage(this.backend, {this.portalUrl, this.portalReady})
      : super(subscriptionRequest: () async => backend.current);

  final _Backend backend;
  final String? portalUrl;
  final Completer<void>? portalReady;
  int portalOpens = 0;

  @override
  Future<Map<String, String>?> openCustomerPortal() async {
    portalOpens++;
    await portalReady?.future;
    return portalUrl == null ? null : {'url': portalUrl!};
  }
}

class _Backend {
  _Backend(this.current);
  UserSubscriptionResponse current;
}

Future<_FakeUsage> _pump(
  WidgetTester tester,
  UserSubscriptionResponse response, {
  String? portalUrl,
  double textScale = 1,
  Completer<void>? portalReady,
  MonthlySwitchApplier? applyMonthlySwitch,
  bool inHomeList = false,
}) async {
  final usage = _FakeUsage(_Backend(response), portalUrl: portalUrl, portalReady: portalReady);
  addTearDown(usage.dispose);
  await usage.fetchSubscription();
  final row = PaymentIssueRow(
    applyMonthlySwitch: applyMonthlySwitch,
    portalPage: (url, onLoaded) => Scaffold(
      body: Column(
        children: [
          Text('portal $url'),
          TextButton(onPressed: onLoaded, child: const Text('Finish loading portal')),
          Builder(
            builder: (context) =>
                TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Back to Omi')),
          ),
        ],
      ),
    ),
  );
  await tester.pumpWidget(
    ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
          child: child!,
        ),
        home: Scaffold(
          body: inHomeList ? CustomScrollView(slivers: [SliverToBoxAdapter(child: row)]) : row,
        ),
      ),
    ),
  );
  return usage;
}

void main() {
  late RecordingAdapter analytics;
  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    analytics = RecordingAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
  });
  tearDown(AnalyticsManager.resetForTesting);

  Future<List<String>> events(WidgetTester tester) async {
    await tester.runAsync(() => AnalyticsManager.flushPending(force: true));
    return analytics.events.map((event) => event.$1).toList();
  }

  testWidgets('a past_due renewal shows one row with Update', (tester) async {
    await _pump(tester, _response(issue: _pastDue));

    expect(find.byKey(const ValueKey('payment_issue_row')), findsOneWidget);
    expect(find.text('Your card was declined'), findsOneWidget);
    expect(find.text('Update it to get Omi Pro back'), findsOneWidget);
    expect(find.text('Update'), findsOneWidget);
  });

  testWidgets('largest text keeps the copy readable and Update reachable on iPhone', (tester) async {
    tester.view.physicalSize = const Size(402, 874);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await _pump(tester, _response(issue: _pastDue), portalUrl: 'https://billing.stripe.com/test', textScale: 3.2);

    expect(tester.takeException(), isNull);
    final message = tester.getRect(find.text('Update it to get Omi Pro back'));
    final update = tester.getRect(find.byKey(const ValueKey('payment_issue_update')));
    expect(update.top, greaterThanOrEqualTo(message.bottom));
    expect(update.right, lessThanOrEqualTo(402));
    expect(update.bottom, lessThanOrEqualTo(874));

    await tester.tap(find.byKey(const ValueKey('payment_issue_update')));
    await tester.pumpAndSettle();
    expect(find.text('portal https://billing.stripe.com/test'), findsOneWidget);
  });

  testWidgets('a legacy plan names that plan, not Omi Pro', (tester) async {
    await _pump(tester, _response(issue: const PaymentIssue(status: 'unpaid', plan: PlanType.operator)));

    expect(find.text('Update it to get Operator back'), findsOneWidget);
  });

  for (final (name, response) in [
    ('active Omi Pro', _response(plan: PlanType.unlimitedV2)),
    ('canceled by choice', _response()),
    ('trial that ended', _response()),
    ('hidden subscription UI', _response(issue: _pastDue, showSubscriptionUi: false)),
  ]) {
    testWidgets('no row for $name', (tester) async {
      await _pump(tester, response);

      expect(find.byKey(const ValueKey('payment_issue_row')), findsNothing);
      expect(find.text('Your card was declined'), findsNothing);
      expect(await events(tester), isEmpty);
    });
  }

  testWidgets('Update opens the billing portal and the row leaves once the invoice is paid', (tester) async {
    final usage =
        await _pump(tester, _response(issue: _pastDue), portalUrl: 'https://billing.stripe.com/p/session/test');

    await tester.tap(find.byKey(const ValueKey('payment_issue_update')));
    await tester.pumpAndSettle();

    expect(usage.portalOpens, 1);
    expect(find.text('portal https://billing.stripe.com/p/session/test'), findsOneWidget);

    // The reader pays in the portal: the next subscription read has no payment issue.
    usage.backend.current = _response(plan: PlanType.unlimitedV2);
    await tester.tap(find.text('Back to Omi'));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('payment_issue_row')), findsNothing);
  });

  testWidgets('a portal that cannot open keeps the row and says so', (tester) async {
    final usage = await _pump(tester, _response(issue: _pastDue));

    await tester.tap(find.byKey(const ValueKey('payment_issue_update')));
    await tester.pumpAndSettle();

    expect(usage.portalOpens, 1);
    expect(find.text('Could not open payment settings. Please try again.'), findsOneWidget);
    expect(find.byKey(const ValueKey('payment_issue_row')), findsOneWidget);
  });

  testWidgets('the row survives a subscription round-trip through toJson', (tester) async {
    final json = _response(issue: _pastDue).toJson();

    expect(json['payment_issue'], {'plan': 'unlimited_v2', 'status': 'past_due', 'monthly_switch': null});
    expect(UserSubscriptionResponse.fromJson(json).paymentIssue, _pastDue);
    expect(UserSubscriptionResponse.fromJson(_response(issue: _yearlyPastDue).toJson()).paymentIssue, _yearlyPastDue);
  });

  testWidgets('a server that predates the offer still yields the Update-only row', (tester) async {
    final json = _response(issue: _pastDue).toJson();
    (json['payment_issue'] as Map<String, dynamic>).remove('monthly_switch');
    final usage = _FakeUsage(_Backend(UserSubscriptionResponse.fromJson(json)));
    addTearDown(usage.dispose);

    expect(UserSubscriptionResponse.fromJson(json).paymentIssue?.monthlySwitch, isNull);
    await _pump(tester, UserSubscriptionResponse.fromJson(json));
    expect(find.byKey(const ValueKey('payment_issue_monthly')), findsNothing);
    expect(find.text('Update it to get Omi Pro back'), findsOneWidget);
  });

  group('declined yearly renewal', () {
    testWidgets('offers the plan monthly price next to Update', (tester) async {
      await _pump(tester, _response(issue: _yearlyPastDue));

      expect(find.text('Your card was declined'), findsOneWidget);
      expect(find.text('Update it, or get Omi Pro back for US\$29.99 a month'), findsOneWidget);
      expect(find.byKey(const ValueKey('payment_issue_monthly')), findsOneWidget);
      expect(find.byKey(const ValueKey('payment_issue_update')), findsOneWidget);
      expect(find.text('Switch to Monthly'), findsOneWidget);
      // Default text: one line, Switch to Monthly then Update at the end.
      final monthly = tester.getRect(find.byKey(const ValueKey('payment_issue_monthly')));
      final update = tester.getRect(find.byKey(const ValueKey('payment_issue_update')));
      expect(monthly.center.dy, closeTo(update.center.dy, 1));
      expect(monthly.right, lessThan(update.left));
      expect(await events(tester), ['Subscription Payment Issue Shown', 'Subscription Payment Issue Monthly Shown']);
    });

    testWidgets('both actions stay on screen and separate for screen readers at the largest text', (tester) async {
      tester.view.physicalSize = const Size(402, 874);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final semantics = tester.ensureSemantics();
      // Home shows the row in its scrolling sliver list (conversations_page.dart), so at this size the
      // row may scroll; nothing inside it may clip and each action must scroll fully into view.
      await _pump(tester, _response(issue: _yearlyPastDue), textScale: 3.2, inHomeList: true);

      expect(tester.takeException(), isNull);
      for (final key in ['payment_issue_monthly', 'payment_issue_update']) {
        await tester.ensureVisible(find.byKey(ValueKey(key)));
        await tester.pumpAndSettle();
        final rect = tester.getRect(find.byKey(ValueKey(key)));
        expect(rect.top, greaterThanOrEqualTo(0));
        expect(rect.right, lessThanOrEqualTo(402));
        expect(rect.bottom, lessThanOrEqualTo(874));
      }
      expect(find.bySemanticsLabel('Switch to Monthly'), findsOneWidget);
      expect(find.bySemanticsLabel('Update'), findsOneWidget);
      // Update, the primary, comes first so it stays clear of Home's pinned Ask bar.
      expect(
        tester.getRect(find.byKey(const ValueKey('payment_issue_update'))).top,
        lessThan(tester.getRect(find.byKey(const ValueKey('payment_issue_monthly'))).top),
      );
      semantics.dispose();
    });

    testWidgets('the sheet shows the plan, what is charged today and the replaced yearly charge', (tester) async {
      await _pump(tester, _response(issue: _yearlyPastDue));
      await tester.tap(find.byKey(const ValueKey('payment_issue_monthly')));
      await tester.pumpAndSettle();

      expect(find.text('Omi Pro, US\$29.99 a month'), findsOneWidget);
      expect(find.text('Due today'), findsOneWidget);
      expect(find.byKey(const Key('monthly_switch_due_today')), findsOneWidget);
      expect(tester.widget<Text>(find.byKey(const Key('monthly_switch_due_today'))).data, 'US\$29.99');
      expect(
          find.text('Replaces the unpaid US\$269.91 yearly charge. Renews monthly. Cancel anytime.'), findsOneWidget);
      expect(find.byKey(const Key('monthly_switch_cancel')), findsOneWidget);
    });

    testWidgets('at the largest text the sheet scrolls and Confirm stays reachable', (tester) async {
      tester.view.physicalSize = const Size(402, 874);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var calls = 0;
      await _pump(tester, _response(issue: _yearlyPastDue), textScale: 3.2, inHomeList: true,
          applyMonthlySwitch: ({required priceId, required expectedAmount}) async {
        calls++;
        return {'error': true, 'status_code': 402};
      });
      await tester.ensureVisible(find.byKey(const ValueKey('payment_issue_monthly')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('payment_issue_monthly')));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      // The amount reads whole, under its label.
      expect(tester.widget<Text>(find.byKey(const Key('monthly_switch_due_today'))).data, 'US\$29.99');
      await tester.ensureVisible(find.byKey(const Key('monthly_switch_confirm')));
      await tester.pumpAndSettle();
      final confirm = tester.getRect(find.byKey(const Key('monthly_switch_confirm')));
      expect(confirm.bottom, lessThanOrEqualTo(874));
      await tester.tap(find.byKey(const Key('monthly_switch_confirm')));
      await tester.pumpAndSettle();
      expect(calls, 1);
      expect(tester.takeException(), isNull);
    });

    testWidgets('Cancel closes the sheet without any request', (tester) async {
      var calls = 0;
      await _pump(tester, _response(issue: _yearlyPastDue),
          applyMonthlySwitch: ({required priceId, required expectedAmount}) async {
        calls++;
        return {'status': 'switched'};
      });
      await tester.tap(find.byKey(const ValueKey('payment_issue_monthly')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('monthly_switch_cancel')));
      await tester.pumpAndSettle();

      expect(calls, 0);
      expect(find.byKey(const Key('monthly_switch_preview')), findsNothing);
      expect(find.byKey(const ValueKey('payment_issue_row')), findsOneWidget);
    });

    testWidgets('Confirm charges only the shown amount once, then the row leaves', (tester) async {
      final requests = <(String, int)>[];
      final answer = Completer<Map<String, dynamic>?>();
      late _FakeUsage usage;
      usage = await _pump(tester, _response(issue: _yearlyPastDue),
          applyMonthlySwitch: ({required priceId, required expectedAmount}) {
        requests.add((priceId, expectedAmount));
        return answer.future;
      });
      await tester.tap(find.byKey(const ValueKey('payment_issue_monthly')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('monthly_switch_confirm')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('monthly_switch_confirm')), warnIfMissed: false);
      await tester.pump();

      expect(requests, [('price_1TuIa81F8wnoWYvw0iX0j5M8', 2999)]);
      usage.backend.current = _response(plan: PlanType.unlimitedV2);
      answer.complete({'status': 'switched', 'message': "You're on monthly now."});
      await tester.pumpAndSettle();

      expect(find.text("You're on monthly"), findsOneWidget);
      expect(find.text('US\$29.99 paid today. Renews monthly.'), findsOneWidget);
      await tester.tap(find.byKey(const Key('monthly_switch_done_button')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('payment_issue_row')), findsNothing);
      expect(await events(tester), [
        'Subscription Payment Issue Shown',
        'Subscription Payment Issue Monthly Shown',
        'Subscription Payment Issue Monthly Tapped',
        'Subscription Payment Issue Monthly Switched',
      ]);
    });

    testWidgets('a declined card says nothing changed and keeps the row and the retry', (tester) async {
      var calls = 0;
      await _pump(tester, _response(issue: _yearlyPastDue),
          applyMonthlySwitch: ({required priceId, required expectedAmount}) async {
        calls++;
        return {'error': true, 'status_code': 402, 'detail': 'Your card was declined.'};
      });
      await tester.tap(find.byKey(const ValueKey('payment_issue_monthly')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('monthly_switch_confirm')));
      await tester.pumpAndSettle();

      expect(find.text("Payment declined. Your plan didn't change."), findsOneWidget);
      expect(find.byKey(const Key('monthly_switch_confirm')), findsOneWidget);
      await tester.tap(find.byKey(const Key('monthly_switch_confirm')));
      await tester.pumpAndSettle();
      expect(calls, 2);

      await tester.tap(find.byKey(const Key('monthly_switch_cancel')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('payment_issue_row')), findsOneWidget);
      final names = await events(tester);
      expect(names.where((name) => name == 'Subscription Payment Issue Monthly Failed').length, 2);
      expect(names, isNot(contains('Subscription Payment Issue Monthly Switched')));
    });

    testWidgets('a refusal hides Confirm and points at Update', (tester) async {
      await _pump(tester, _response(issue: _yearlyPastDue),
          applyMonthlySwitch: ({required priceId, required expectedAmount}) async =>
              {'error': true, 'status_code': 409});
      await tester.tap(find.byKey(const ValueKey('payment_issue_monthly')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('monthly_switch_confirm')));
      await tester.pumpAndSettle();

      expect(find.text("Switching isn't available right now. Update your card instead."), findsOneWidget);
      expect(find.byKey(const Key('monthly_switch_confirm')), findsNothing);
      expect(find.byKey(const Key('monthly_switch_cancel')), findsOneWidget);
    });

    testWidgets('no answer reads the plan again before claiming a switch', (tester) async {
      late _FakeUsage usage;
      usage = await _pump(tester, _response(issue: _yearlyPastDue),
          applyMonthlySwitch: ({required priceId, required expectedAmount}) async {
        usage.backend.current = _response(plan: PlanType.unlimitedV2); // it landed; the answer was lost
        return null;
      });
      await tester.tap(find.byKey(const ValueKey('payment_issue_monthly')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('monthly_switch_confirm')));
      await tester.pumpAndSettle();

      expect(find.text("You're on monthly"), findsOneWidget);
    });

    testWidgets('no answer and no change says so and keeps the retry', (tester) async {
      await _pump(tester, _response(issue: _yearlyPastDue),
          applyMonthlySwitch: ({required priceId, required expectedAmount}) async => null);
      await tester.tap(find.byKey(const ValueKey('payment_issue_monthly')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('monthly_switch_confirm')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('monthly_switch_error')), findsOneWidget);
      expect(find.text("You're on monthly"), findsNothing);
      expect(find.byKey(const Key('monthly_switch_confirm')), findsOneWidget);
    });
  });

  testWidgets('shown counts a visible issue once across refreshes and again after it reappears', (tester) async {
    final usage = await _pump(tester, _response(issue: _pastDue));
    await usage.fetchSubscription();
    await tester.pump();
    expect(await events(tester), ['Subscription Payment Issue Shown']);

    usage.backend.current = _response();
    await usage.fetchSubscription();
    await tester.pump();
    usage.backend.current = _response(issue: _pastDue);
    await usage.fetchSubscription();
    await tester.pump();
    expect(await events(tester), ['Subscription Payment Issue Shown', 'Subscription Payment Issue Shown']);
  });

  testWidgets('tapped counts once and portal opened waits for successful page load', (tester) async {
    final portalReady = Completer<void>();
    await _pump(tester, _response(issue: _pastDue),
        portalUrl: 'https://billing.stripe.com/test', portalReady: portalReady);
    await tester.tap(find.byKey(const ValueKey('payment_issue_update')));
    await tester.tap(find.byKey(const ValueKey('payment_issue_update')));
    portalReady.complete();
    await tester.pumpAndSettle();

    expect(await events(tester), ['Subscription Payment Issue Shown', 'Subscription Payment Issue Update Tapped']);
    await tester.tap(find.text('Finish loading portal'));
    await tester.pump();
    expect(await events(tester), [
      'Subscription Payment Issue Shown',
      'Subscription Payment Issue Update Tapped',
      'Subscription Payment Issue Portal Opened',
    ]);
    expect(analytics.events.every((event) => event.$1.toLowerCase().contains('subscri')), isTrue);
  });

  testWidgets('a failed portal attempt has no opened event and keeps the visible issue', (tester) async {
    await _pump(tester, _response(issue: _pastDue));
    await tester.tap(find.byKey(const ValueKey('payment_issue_update')));
    await tester.pumpAndSettle();

    expect(await events(tester), ['Subscription Payment Issue Shown', 'Subscription Payment Issue Update Tapped']);
    expect(find.byKey(const ValueKey('payment_issue_row')), findsOneWidget);
  });
}
