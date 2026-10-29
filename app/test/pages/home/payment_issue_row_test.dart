import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/home/widgets/payment_issue_row.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

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

/// The backend answer and the portal are fakes; the row, its opener and the refresh are real.
class _FakeUsage extends UsageProvider {
  _FakeUsage(this.backend, {this.portalUrl}) : super(subscriptionRequest: () async => backend.current);

  final _Backend backend;
  final String? portalUrl;
  int portalOpens = 0;

  @override
  Future<Map<String, String>?> openCustomerPortal() async {
    portalOpens++;
    return portalUrl == null ? null : {'url': portalUrl!};
  }
}

class _Backend {
  _Backend(this.current);
  UserSubscriptionResponse current;
}

Future<_FakeUsage> _pump(WidgetTester tester, UserSubscriptionResponse response, {String? portalUrl}) async {
  final usage = _FakeUsage(_Backend(response), portalUrl: portalUrl);
  addTearDown(usage.dispose);
  await usage.fetchSubscription();
  await tester.pumpWidget(
    ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: PaymentIssueRow(
            portalPage: (url) => Scaffold(
              body: Column(
                children: [
                  Text('portal $url'),
                  Builder(
                    builder: (context) =>
                        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Back to Omi')),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );
  return usage;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('a past_due renewal shows one row with Update', (tester) async {
    await _pump(tester, _response(issue: _pastDue));

    expect(find.byKey(const ValueKey('payment_issue_row')), findsOneWidget);
    expect(find.text('Your card was declined'), findsOneWidget);
    expect(find.text('Update it to keep Omi Pro'), findsOneWidget);
    expect(find.text('Update'), findsOneWidget);
  });

  testWidgets('a legacy plan names that plan, not Omi Pro', (tester) async {
    await _pump(tester, _response(issue: const PaymentIssue(status: 'unpaid', plan: PlanType.operator)));

    expect(find.text('Update it to keep Operator'), findsOneWidget);
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

    expect(json['payment_issue'], {'plan': 'unlimited_v2', 'status': 'past_due'});
    expect(UserSubscriptionResponse.fromJson(json).paymentIssue, _pastDue);
  });
}
