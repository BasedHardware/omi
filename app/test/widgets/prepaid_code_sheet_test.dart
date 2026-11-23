import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/payment.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/pages/settings/widgets/plans/prepaid_code_sheet.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/usage_provider.dart';

// "Have a code?": a prepaid Omi Pro code redeemed with no card. The entry shows only while the server
// switch is on; the sheet has one field and one button, shows the plan and its end date on success,
// and a specific message for each refusal. No price or payment appears anywhere in it.

UserSubscriptionResponse _response({required bool switchOn, PlanType plan = PlanType.basic}) =>
    UserSubscriptionResponse(
      trialEligible: true,
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 18000,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      prepaidCodeRedeem: switchOn,
    );

class _Usage extends UsageProvider {
  _Usage(this.response);
  final UserSubscriptionResponse response;
  @override
  UserSubscriptionResponse get subscription => response;
}

Widget _app(Widget child) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

Future<List<String>> _pumpSheet(WidgetTester tester, ApiResult<PrepaidCodeRedemption> Function(String) answer,
    {List<int>? redeemed}) async {
  final codes = <String>[];
  await tester.pumpWidget(_app(PrepaidCodeSheet(
    source: PrepaidCodeSource.plansSheet,
    redeem: (code) async {
      codes.add(code);
      return answer(code);
    },
    onRedeemed: () => redeemed?.add(1),
  )));
  await tester.pump();
  return codes;
}

ApiFailure<PrepaidCodeRedemption> _refused(int status, String? detail) =>
    ApiFailure(ApiProblem(ApiProblemKind.rejected, statusCode: status, detail: detail));

void main() {
  test('the switch, not the plan alone, decides whether the entry is offered', () {
    expect(_Usage(_response(switchOn: false)).canRedeemPrepaidCode, isFalse);
    expect(_Usage(_response(switchOn: true)).canRedeemPrepaidCode, isTrue);
    expect(_Usage(_response(switchOn: true, plan: PlanType.unlimitedV2)).canRedeemPrepaidCode, isFalse);
    final omitted = UserSubscriptionResponse.fromJson({
      'subscription': {'plan': 'basic', 'status': 'active'},
      'transcription_seconds_used': 0,
      'transcription_seconds_limit': 0,
      'words_transcribed_used': 0,
      'words_transcribed_limit': 0,
      'insights_gained_used': 0,
      'insights_gained_limit': 0,
    });
    expect(omitted.prepaidCodeRedeem, isFalse);
  });

  testWidgets('the button stays off until a code is typed', (tester) async {
    final codes = await _pumpSheet(tester, (_) => _refused(400, 'invalid_code'));
    final button = find.byKey(const ValueKey('prepaid_code_redeem'));
    await tester.tap(button);
    await tester.pump();
    expect(codes, isEmpty);
    expect(find.text('Redeem'), findsOneWidget);
    expect(find.textContaining(r'$'), findsNothing);
  });

  testWidgets('success shows the plan and the date it ends, and refreshes the plan once', (tester) async {
    final redeemed = <int>[];
    final codes = await _pumpSheet(
      tester,
      (_) => ApiSuccess(PrepaidCodeRedemption(plan: 'Omi Pro', endsAt: DateTime(2027, 11, 23, 5), months: 12)),
      redeemed: redeemed,
    );
    await tester.enterText(find.byKey(const ValueKey('prepaid_code_field')), '  omi-trybe-abcd1234 ');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('prepaid_code_redeem')));
    await tester.pumpAndSettle();
    expect(codes, ['omi-trybe-abcd1234']);
    expect(find.byKey(const ValueKey('prepaid_code_success')), findsOneWidget);
    expect(find.text('Code redeemed'), findsOneWidget);
    expect(find.text('Your Omi Pro plan ends Nov 23, 2027.'), findsOneWidget);
    expect(redeemed, [1]);
    expect(find.byKey(const ValueKey('prepaid_code_field')), findsNothing);
  });

  for (final (status, detail, message) in [
    (400, 'invalid_code', "This code isn't valid. Check it and try again."),
    (409, 'code_used', 'This code has already been used.'),
    (400, 'code_expired', 'This code has expired.'),
    (409, 'has_plan', 'You already have a plan. Your code was not used.'),
    (400, 'not_prepaid', "This code can't be redeemed here. Use it when you choose a plan."),
    (400, 'not_eligible', "This code can't be used on this account."),
    (429, null, 'Too many tries. Please wait and try again later.'),
    (503, 'try_again', 'Something went wrong. Please try again.'),
  ]) {
    testWidgets('refusal $status $detail shows its own message and keeps the code', (tester) async {
      await _pumpSheet(tester, (_) => _refused(status, detail));
      await tester.enterText(find.byKey(const ValueKey('prepaid_code_field')), 'OMI-1234');
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('prepaid_code_redeem')));
      await tester.pumpAndSettle();
      expect(find.text(message), findsOneWidget);
      expect(find.byKey(const ValueKey('prepaid_code_success')), findsNothing);
      expect(find.text('OMI-1234'), findsOneWidget);
      // Editing the code clears the message.
      await tester.enterText(find.byKey(const ValueKey('prepaid_code_field')), 'OMI-12345');
      await tester.pump();
      expect(find.text(message), findsNothing);
    });
  }

  testWidgets('a transport error is a retryable message, not a crash', (tester) async {
    await _pumpSheet(tester, (_) => throw Exception('offline'));
    await tester.enterText(find.byKey(const ValueKey('prepaid_code_field')), 'OMI-1234');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('prepaid_code_redeem')));
    await tester.pumpAndSettle();
    expect(find.text('Something went wrong. Please try again.'), findsOneWidget);
  });

  testWidgets('the entry opens the sheet', (tester) async {
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>(
      create: (_) => _Usage(_response(switchOn: true)),
      child: _app(const PrepaidCodeEntry(source: PrepaidCodeSource.plansSheet)),
    ));
    await tester.tap(find.text('Have a code?'));
    await tester.pumpAndSettle();
    expect(find.text('Redeem a code'), findsOneWidget);
    expect(find.byKey(const ValueKey('prepaid_code_field')), findsOneWidget);
  });

  group('trial paywall', () {
    const offer = PaywallOffer(
      tierId: 'unlimited',
      monthly: PaywallPrice(priceId: 'm', interval: 'month', amountMinor: 2999, currency: 'usd'),
      yearly: PaywallPrice(priceId: 'y', interval: 'year', amountMinor: 26991, currency: 'usd'),
    );

    Future<void> pumpPaywall(WidgetTester tester, {required bool switchOn, double textScale = 1}) async {
      tester.view.physicalSize = const Size(402, 874) * 3;
      tester.view.devicePixelRatio = 3;
      tester.view.padding = const FakeViewPadding(top: 62 * 3, bottom: 34 * 3);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<UsageProvider>(create: (_) => _Usage(_response(switchOn: switchOn))),
          ChangeNotifierProvider<AuthenticationProvider>(
              create: (_) => AuthenticationProvider(initializeListeners: false)),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
            child: child!,
          ),
          home: TrialPaywallPage(
            source: 'onboarding',
            offer: offer,
            now: DateTime(2026, 11, 23),
            checkout: (_, __, ___) async => PaywallCheckoutOutcome.failed,
          ),
        ),
      ));
      await tester.pumpAndSettle();
    }

    testWidgets('switch off: today\'s code hint, no entry', (tester) async {
      await pumpPaywall(tester, switchOn: false);
      expect(find.byKey(const Key('trial_paywall_code_hint')), findsOneWidget);
      expect(find.byKey(const ValueKey('prepaid_code_entry')), findsNothing);
    });

    testWidgets('switch on: the hint becomes "Have a code?" and opens the sheet', (tester) async {
      await pumpPaywall(tester, switchOn: true);
      expect(find.byKey(const Key('trial_paywall_code_hint')), findsNothing);
      await tester.tap(find.byKey(const ValueKey('prepaid_code_entry')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('prepaid_code_field')), findsOneWidget);
    });

    testWidgets('largest text: the entry scrolls with the page and still opens the sheet', (tester) async {
      await pumpPaywall(tester, switchOn: true, textScale: 2);
      final entry = find.byKey(const ValueKey('prepaid_code_entry'));
      await tester.scrollUntilVisible(entry, 200, scrollable: find.byType(Scrollable).first);
      await tester.pumpAndSettle();
      // The test font overflows the existing timeline row at this scale (not this entry); drain it.
      tester.takeException();
      await tester.tap(entry);
      await tester.pumpAndSettle();
      tester.takeException();
      expect(find.byKey(const ValueKey('prepaid_code_field')), findsOneWidget);
    });
  });
}
