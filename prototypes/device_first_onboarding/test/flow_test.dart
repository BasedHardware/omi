import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device_first_prototype/main.dart';
import 'package:omi_device_first_prototype/src/content.dart';
import 'package:omi_device_first_prototype/src/flow.dart';
import 'package:omi_device_first_prototype/src/theme.dart';

Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 150));
  }
}

Future<void> pumpFlow(
  WidgetTester tester, {
  DfDirection direction = DfDirection.graphite,
  TrialLength trial = TrialLength.oneMonth,
  DfStep step = DfStep.welcome,
  Size size = const Size(390, 844),
  Duration searchDuration = const Duration(milliseconds: 200),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: DeviceFirstFlow(direction: direction, trial: trial, initialStep: step, searchDuration: searchDuration),
    ),
  );
  await settle(tester);
}

Future<void> tapText(WidgetTester tester, String text) async {
  final finder = find.text(text);
  expect(finder, findsOneWidget, reason: 'expected exactly one "$text" on screen');
  await tester.ensureVisible(finder);
  await tester.pump();
  await tester.tap(finder);
  await settle(tester);
}

void main() {
  // One test per screen, so a layout overflow is attributed to the screen that caused it.
  group('every screen renders without overflow', () {
    for (final size in const <Size>[Size(390, 844), Size(375, 667)]) {
      for (final direction in DfDirection.values) {
        for (final step in DfStep.values) {
          testWidgets('${direction.label} ${size.width.toInt()}x${size.height.toInt()} ${step.title}', (tester) async {
            await pumpFlow(
              tester,
              direction: direction,
              step: step,
              size: size,
              searchDuration: const Duration(hours: 1),
            );
            expect(tester.takeException(), isNull);
          });
        }
      }
    }
  });

  testWidgets('has-an-Omi path pairs, onboards and starts a trial', (tester) async {
    await pumpFlow(tester);
    await tapText(tester, 'Get Started');
    await tapText(tester, 'Continue with Apple');
    await tapText(tester, 'Agree & Continue');
    await tapText(tester, 'Yes, pair my Omi');
    await settle(tester);
    expect(find.text('We found your Omi'), findsOneWidget);
    await tapText(tester, 'Pair this Omi');
    expect(find.text('PAIRING SUCCESSFUL'), findsOneWidget);
    await tapText(tester, 'Continue');

    await tester.enterText(find.byType(TextField), 'Nick');
    await settle(tester);
    await tapText(tester, 'Continue');
    await tapText(tester, 'Continue');
    await tapText(tester, 'Continue');
    for (var i = 0; i < 4; i++) {
      await tapText(tester, 'Skip Question');
    }

    expect(find.text('Setting up your Omi, Nick'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
    await settle(tester);
    await tapText(tester, 'See my plan');
    expect(find.text('Your Omi is ready, Nick'), findsOneWidget);
    await tapText(tester, 'Continue');

    expect(find.text('FOR NICK'), findsOneWidget);
    expect(find.text('Your first month of Unlimited is free.'), findsOneWidget);
    await tapText(tester, 'Start my free month');
    expect(find.text("You're all set, Nick."), findsOneWidget);
    await tapText(tester, 'Start Using Omi');
    expect(find.text('Trial started · yearly · 30 days'), findsOneWidget);
  });

  testWidgets('"See my plan" stays disabled until setup finishes', (tester) async {
    await pumpFlow(tester, step: DfStep.setup);
    await tester.tap(find.text('See my plan'));
    await settle(tester);
    expect(find.text('See my plan'), findsOneWidget, reason: 'still on the setup screen');
  });

  testWidgets('no-Omi path goes buy, checkout, waiting room, then pairing', (tester) async {
    await pumpFlow(tester, step: DfStep.fork, searchDuration: const Duration(hours: 1));
    await tapText(tester, "I don't have one yet");
    expect(find.text(r'$129'), findsOneWidget);
    expect(find.text(r'$179'), findsOneWidget);
    await tapText(tester, r'Buy Omi — $129');
    expect(find.text('Order summary'), findsOneWidget);
    await tapText(tester, 'Pay with Apple Pay');
    expect(find.text('Your Omi is on its way.'), findsOneWidget);
    await tapText(tester, 'It arrived — pair my Omi');
    expect(find.text('Turn on your Omi'), findsOneWidget);
  });

  testWidgets('"It\'s on the way" waits, then the delivery push opens pairing', (tester) async {
    await pumpFlow(tester, step: DfStep.fork, searchDuration: const Duration(hours: 1));
    await tapText(tester, "It's on the way");
    expect(find.text('Your Omi is on its way.'), findsOneWidget);
    await tapText(tester, 'Track order');
    await tapText(tester, 'Your Omi has arrived');
    expect(find.text('Turn on your Omi'), findsOneWidget);
  });

  group('paywall copy follows the trial arm', () {
    for (final trial in TrialLength.values) {
      testWidgets(trial.label, (tester) async {
        await pumpFlow(tester, step: DfStep.paywall, trial: trial);
        expect(find.text(trial.headline), findsOneWidget);
        expect(find.text(trial.cta), findsOneWidget);
        expect(find.text('Day ${trial.reminderDay}'), findsOneWidget);
        expect(find.text('Day ${trial.days}'), findsOneWidget);
        expect(find.text('\$0 today · Cancel anytime before day ${trial.days}'), findsOneWidget);
        await tapText(tester, 'Continue with Free');
        expect(find.text('Continued with Free'), findsOneWidget);
      });
    }
  });

  testWidgets('choosing Monthly starts a monthly trial', (tester) async {
    await pumpFlow(tester, step: DfStep.paywall, trial: TrialLength.oneWeek);
    await tapText(tester, 'Monthly');
    await tapText(tester, 'Start my free week');
    await tapText(tester, 'Start Using Omi');
    expect(find.text('Trial started · monthly · 7 days'), findsOneWidget);
  });

  testWidgets('launcher opens the flow in the chosen direction and trial arm', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const DeviceFirstPrototypeApp());
    await settle(tester);
    await tapText(tester, 'Aurora');
    await tapText(tester, '14 days');
    await tapText(tester, 'Play the flow');
    expect(find.text('Get Started'), findsOneWidget);
    final flow = tester.widget<DeviceFirstFlow>(find.byType(DeviceFirstFlow));
    expect(flow.direction, DfDirection.aurora);
    expect(flow.trial, TrialLength.twoWeeks);
  });
}
