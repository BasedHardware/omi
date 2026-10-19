import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device_first_prototype/src/app/app_gallery.dart';
import 'package:omi_device_first_prototype/src/app/app_shell.dart';
import 'package:omi_device_first_prototype/src/content.dart';
import 'package:omi_device_first_prototype/src/theme.dart';

import 'support.dart';

Future<void> pumpApp(
  WidgetTester tester, {
  DfDirection direction = DfDirection.auroraLight,
  DfPlanState plan = const DfPlanState.free(),
  WidgetBuilder? home,
  Size size = const Size(390, 844),
}) async {
  setSize(tester, size);
  final theme = DfTheme.of(direction);
  await tester.pumpWidget(
    MaterialApp(
      home: DfThemeScope(
        theme: theme,
        child: Scaffold(body: OmiApp(plan: plan, today: testToday, home: home)),
      ),
    ),
  );
  await settle(tester);
}

void main() {
  group('every app screen renders without overflow', () {
    for (final size in const <Size>[Size(390, 844), Size(375, 667)]) {
      for (final direction in DfDirection.values) {
        for (final (title, builder) in appScreens) {
          testWidgets('${direction.label} ${size.width.toInt()}x${size.height.toInt()} $title', (tester) async {
            await pumpApp(tester, direction: direction, home: builder, size: size);
            expect(tester.takeException(), isNull);
          });
        }
      }
    }
    for (final (title, builder) in appScreens) {
      testWidgets('Unlimited 375x667 $title', (tester) async {
        await pumpApp(tester, plan: const DfPlanState.trial(7), home: builder, size: const Size(375, 667));
        expect(tester.takeException(), isNull);
      });
    }
  });

  testWidgets('Free home locks older conversations; upgrading unlocks them', (tester) async {
    await pumpApp(tester);
    expect(find.text('Free plan'), findsOneWidget);
    expect(find.text('214 of 300 min used this month'), findsOneWidget);
    expect(find.text('Call with the landlord'), findsNothing);

    await scrollTo(tester, find.text('Upgrade to Unlimited'));
    await tapText(tester, 'Upgrade to Unlimited');
    expect(find.text('How your free trial works.', findRichText: true), findsOneWidget);
    await tapText(tester, r'Try for $0.00');
    expect(find.text('Try free for 30 days'), findsOneWidget);
    await tapText(tester, 'Start trial');

    expect(find.text('Free plan'), findsNothing);
    await scrollTo(tester, find.text('Call with the landlord'));
    expect(find.text('Call with the landlord'), findsOneWidget);
  });

  testWidgets('closing the in-app paywall keeps Free', (tester) async {
    await pumpApp(tester);
    await tapText(tester, 'Upgrade');
    await tapTooltip(tester, 'Close');
    expect(find.text('Free plan'), findsOneWidget);
  });

  testWidgets('conversation opens with summary, action items and transcript', (tester) async {
    await pumpApp(tester);
    await tapText(tester, 'Launch timing with Maya');
    expect(find.text('Overview'), findsOneWidget);
    expect(find.text('Send Maya the revised deck'), findsOneWidget);
    await tapText(tester, 'Send Maya the revised deck');
    expect(tester.getSemantics(find.bySemanticsLabel('Send Maya the revised deck')), isSemantics(isChecked: true));
    await tapText(tester, 'Transcript');
    expect(find.text('Thursday works if QA signs off by Wednesday.'), findsOneWidget);
    await tapTooltip(tester, 'Back');
    expect(find.text('Ask Omi'), findsOneWidget);
  });

  testWidgets('tasks: complete one and add a new one', (tester) async {
    await pumpApp(tester);
    await tapText(tester, 'Tasks');
    expect(find.text('Overdue'), findsOneWidget);
    expect(find.text('Today'), findsOneWidget);

    await tapText(tester, 'New Task');
    await tester.enterText(find.byType(TextField), 'Call the plumber');
    await settle(tester);
    await tapFinder(tester, find.descendant(of: find.byType(NewTaskSheet), matching: find.text('Tomorrow')));
    await tapText(tester, 'Add task');
    expect(find.text('Call the plumber'), findsOneWidget);
    await tapText(tester, 'Sign the lease renewal');
    expect(tester.getSemantics(find.bySemanticsLabel('Sign the lease renewal')), isSemantics(isChecked: true));
  });

  testWidgets('Ask Omi answers a suggestion with sources', (tester) async {
    await pumpApp(tester);
    await tapText(tester, 'Ask Omi');
    expect(find.text('Hi Alex'), findsOneWidget);
    await tapText(tester, 'What do I still owe people?');
    expect(find.textContaining('Maya: the revised deck, by Friday.'), findsOneWidget);
    expect(find.textContaining('Coffee with Sam'), findsOneWidget);
  });

  testWidgets('search filters conversations and switches to people', (tester) async {
    await pumpApp(tester);
    await tapTooltip(tester, 'Search');
    await tester.enterText(find.byType(TextField), 'seed');
    await settle(tester);
    expect(find.text('Coffee with Sam about the seed round'), findsOneWidget);
    expect(find.text('Launch timing with Maya'), findsNothing);
    await tester.enterText(find.byType(TextField), '');
    await tapText(tester, 'People');
    expect(find.text('Maya'), findsOneWidget);
  });

  testWidgets('settings reach plan, device, memories and integrations', (tester) async {
    await pumpApp(tester);
    await tapTooltip(tester, 'Settings');
    await tapText(tester, 'Plan & Usage');
    expect(find.text('214 min'), findsOneWidget);
    await tapText(tester, 'All Time');
    expect(find.text('44 h'), findsOneWidget);
    await tapTooltip(tester, 'Back');

    await tapText(tester, 'Device');
    expect(find.text("Alex's Omi"), findsOneWidget);
    await tapTooltip(tester, 'Back');

    await tapText(tester, 'Memories');
    await tapText(tester, 'People');
    expect(find.text('Maya runs support and launch communications'), findsOneWidget);
    expect(find.text('Prefers deep work in the mornings'), findsNothing);
    await tapTooltip(tester, 'Back');

    await tapText(tester, 'Integrations');
    await tapText(tester, 'Notion');
    await tapText(tester, 'Enable');
    expect(find.text('Disable'), findsOneWidget);
  });

  testWidgets('the device pill opens the device page', (tester) async {
    await pumpApp(tester);
    await tapFinder(tester, find.bySemanticsLabel('Omi, connected, 82% battery'));
    expect(find.text('Connected · 82% battery'), findsOneWidget);
  });

  testWidgets('pausing listening updates the capture card', (tester) async {
    await pumpApp(tester);
    expect(find.text('Listening'), findsOneWidget);
    await tapTooltip(tester, 'Pause listening');
    expect(find.text('Paused'), findsOneWidget);
  });

  testWidgets('controls outside the prototype explain themselves', (tester) async {
    await pumpApp(tester);
    await tapTooltip(tester, 'Calendar');
    expect(find.textContaining('isn’t part of this prototype'), findsOneWidget);
  });
}
