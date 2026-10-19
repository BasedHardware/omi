import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device_first_prototype/main.dart';
import 'package:omi_device_first_prototype/src/content.dart';
import 'package:omi_device_first_prototype/src/theme.dart';
import 'package:omi_device_first_prototype/src/v2/paywall_first_flow.dart';
import 'package:omi_device_first_prototype/src/v2/paywall_first_screens.dart';
import 'package:omi_device_first_prototype/src/widgets.dart';

import 'support.dart';

Future<void> pumpV2(
  WidgetTester tester, {
  DfDirection direction = DfDirection.auroraLight,
  TrialLength trial = TrialLength.oneWeek,
  V2Step step = V2Step.welcome,
  Size size = const Size(390, 844),
  Duration searchDuration = const Duration(milliseconds: 200),
}) async {
  setSize(tester, size);
  await tester.pumpWidget(
    MaterialApp(
      home: PaywallFirstFlow(
        direction: direction,
        trial: trial,
        today: testToday,
        initialStep: step,
        searchDuration: searchDuration,
      ),
    ),
  );
  await settle(tester);
}

const String permissionsTitle = "Let's set you up for the best Omi experience";

final Finder toggles = find.byType(DfToggle);

Future<void> sheetClose(WidgetTester tester, Type sheet) =>
    tapFinder(tester, find.descendant(of: find.byType(sheet), matching: find.byTooltip('Close')));

void main() {
  group('every paywall-first screen renders without overflow', () {
    for (final size in const <Size>[Size(390, 844), Size(375, 667)]) {
      for (final direction in DfDirection.values) {
        for (final step in V2Step.values) {
          testWidgets('${direction.label} ${size.width.toInt()}x${size.height.toInt()} ${step.title}', (tester) async {
            await pumpV2(tester,
                direction: direction, step: step, size: size, searchDuration: const Duration(hours: 1));
            expect(tester.takeException(), isNull);
          });
        }
      }
    }
  });

  testWidgets('sign-in leads straight to the paywall', (tester) async {
    await pumpV2(tester);
    expect(find.text('Capture your day, remember everything, & act on it'), findsOneWidget);
    await tapText(tester, 'Continue with Apple');
    expect(find.text('Unlimited'), findsOneWidget);
    expect(find.text(r'Try for $0.00'), findsOneWidget);
    expect(find.text('Try with App Store'), findsOneWidget);
    expect(find.text('Cancel anytime, no penalties or fees'), findsOneWidget);
  });

  group('the paywall timeline is dated from today for each arm', () {
    for (final trial in DfOffer.paywallFirstArms) {
      testWidgets(trial.label, (tester) async {
        await pumpV2(tester, trial: trial, step: V2Step.paywall);
        final reminder = DfOffer.reminderDayFor(trial.days);
        expect(find.text('Today'), findsOneWidget);
        expect(find.text('+${DfOffer.trialPhrase(trial.days)} free'), findsOneWidget);
        expect(find.text('In $reminder days'), findsOneWidget);
        expect(find.text('In ${trial.days} days'), findsOneWidget);
        expect(find.text('Oct 19'), findsOneWidget);
        expect(find.text(dfShortDate(testToday.add(Duration(days: reminder)))), findsOneWidget);
        expect(find.text(dfShortDate(testToday.add(Duration(days: trial.days)))), findsNWidgets(2));
      });
    }
  });

  testWidgets('closing the paywall shows the 30-day winback once; declining goes to setup', (tester) async {
    await pumpV2(tester, step: V2Step.paywall);
    await tapTooltip(tester, 'Close');
    expect(find.text("You've been upgraded to\n30 days free"), findsOneWidget);
    expect(find.text('7 days'), findsOneWidget, reason: 'the original arm, struck through');
    expect(find.text('Until Nov 18, 2026'), findsOneWidget);
    expect(find.text(r'No charge until Nov 18, 2026, then $269/yr.'), findsOneWidget);
    await tapText(tester, 'No thanks');
    expect(find.text(permissionsTitle), findsOneWidget);
  });

  testWidgets('claiming the winback opens web checkout for 30 days', (tester) async {
    await pumpV2(tester, step: V2Step.paywall);
    await tapTooltip(tester, 'Close');
    await tapText(tester, 'Claim my 30-day trial');
    expect(find.text('Pay via web'), findsOneWidget);
    expect(find.text('Try free for 30 days'), findsOneWidget);
    expect(find.text(r'Total due today'), findsOneWidget);
    await tapText(tester, 'Start trial');
    expect(find.text(permissionsTitle), findsOneWidget);
  });

  testWidgets('"Try for \$0.00" opens web checkout for the arm; closing returns to the paywall', (tester) async {
    await pumpV2(tester, step: V2Step.paywall, trial: TrialLength.twoWeeks);
    await tapText(tester, r'Try for $0.00');
    expect(find.text('Try free for 2 weeks'), findsOneWidget);
    expect(find.text('After trial ends on Nov 2, 2026'), findsOneWidget);
    await sheetClose(tester, WebCheckoutSheet);
    expect(find.text('Pay via web'), findsNothing);
    expect(find.text(r'Try for $0.00'), findsOneWidget);
  });

  testWidgets('App Store purchase goes to setup', (tester) async {
    await pumpV2(tester, step: V2Step.paywall, trial: TrialLength.threeDays);
    await tapText(tester, 'Try with App Store');
    expect(find.text('3 days free trial'), findsOneWidget);
    expect(find.text('Starting Oct 22, 2026'), findsOneWidget);
    await tapText(tester, 'Subscribe');
    expect(find.text(permissionsTitle), findsOneWidget);
  });

  testWidgets('Bluetooth is required before setup continues', (tester) async {
    await pumpV2(tester, step: V2Step.permissions);
    await tapText(tester, 'Continue');
    expect(find.text(permissionsTitle), findsOneWidget, reason: 'Continue is disabled');

    await tapFinder(tester, toggles.first);
    await tapText(tester, "Don't Allow");
    await tapText(tester, 'Continue');
    expect(find.text(permissionsTitle), findsOneWidget, reason: 'still disabled after "Don\'t Allow"');

    await tapFinder(tester, toggles.first);
    await tapText(tester, 'Allow');
    await tapText(tester, 'Continue');
    expect(find.text("Let's get your Omi set up"), findsOneWidget);
  });

  testWidgets('declining everything still pairs and lands in the app on Free', (tester) async {
    await pumpV2(tester);
    await tapText(tester, 'Continue with Google');
    await tapTooltip(tester, 'Close');
    await tapText(tester, 'No thanks');

    await tapFinder(tester, toggles.first);
    await tapText(tester, 'Allow');
    await tapText(tester, 'Continue');
    await tapText(tester, 'Continue');
    await settle(tester);
    await tapText(tester, 'Pair this Omi');
    await tapText(tester, 'Continue');
    await tester.enterText(find.byType(TextField), 'Nik');
    await settle(tester);
    await tapText(tester, 'Continue');
    for (var i = 0; i < 4; i++) {
      await tapText(tester, 'Skip Question');
    }
    await tester.pump(const Duration(seconds: 3));
    await settle(tester);
    await tapText(tester, 'Continue');
    expect(find.text('Your Omi is ready, Nik'), findsOneWidget);
    await tapText(tester, 'Open Omi');

    expect(find.text('Ask Omi'), findsOneWidget);
    expect(find.text('Free plan'), findsOneWidget);
    await scrollTo(tester, find.text('2 older conversations are locked'));
    expect(find.text('2 older conversations are locked'), findsOneWidget);
  });

  testWidgets('a trial started on the paywall carries into the app', (tester) async {
    await pumpV2(tester, step: V2Step.paywall);
    await tapText(tester, r'Try for $0.00');
    await tapText(tester, 'Start trial');
    await tapFinder(tester, toggles.first);
    await tapText(tester, 'Allow');
    await tapText(tester, 'Continue');
    await tapText(tester, 'Continue');
    await settle(tester);
    await tapText(tester, 'Pair this Omi');
    await tapText(tester, 'Continue');
    await tester.enterText(find.byType(TextField), 'Nik');
    await settle(tester);
    await tapText(tester, 'Continue');
    for (var i = 0; i < 4; i++) {
      await tapText(tester, 'Skip Question');
    }
    await tester.pump(const Duration(seconds: 3));
    await settle(tester);
    await tapText(tester, 'Continue');
    await tapText(tester, 'Open Omi');
    expect(find.text('Free plan'), findsNothing);
    await scrollTo(tester, find.text('Call with the landlord'));
    expect(find.text('Call with the landlord'), findsOneWidget, reason: 'older conversations are unlocked');
  });

  testWidgets('"I don\'t have my Omi yet" leads to buying one', (tester) async {
    await pumpV2(tester, step: V2Step.setupIntro);
    await tapText(tester, "I don't have my Omi yet");
    expect(find.text('Omi works with its pendant.'), findsOneWidget);
  });

  testWidgets('"Get one now" buys, waits, then pairs', (tester) async {
    await pumpV2(tester, searchDuration: const Duration(hours: 1));
    await tapText(tester, 'Get one now');
    expect(find.text('Omi works with its pendant.'), findsOneWidget);
    await tapText(tester, r'Buy Omi — $129');
    await tapText(tester, 'Pay with Apple Pay');
    await tapText(tester, 'It arrived — pair my Omi');
    expect(find.text('Turn on your Omi'), findsOneWidget);
  });

  testWidgets('launcher opens the paywall-first flow in Aurora Light by default', (tester) async {
    setSize(tester, const Size(390, 844));
    await tester.pumpWidget(const DeviceFirstPrototypeApp());
    await settle(tester);
    await tapText(tester, '14 days');
    await tapText(tester, 'Play the flow');
    final flow = tester.widget<PaywallFirstFlow>(find.byType(PaywallFirstFlow));
    expect(flow.direction, DfDirection.auroraLight);
    expect(flow.trial, TrialLength.twoWeeks);
    expect(find.text('Say hello to Omi'), findsOneWidget);
  });
}
