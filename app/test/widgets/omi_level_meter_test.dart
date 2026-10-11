import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/ui.dart';

void main() {
  Color stepColor(WidgetTester tester, int step) {
    final container = tester.widget<AnimatedContainer>(find.byKey(ValueKey('omi_level_meter_step_$step')));
    return (container.decoration! as BoxDecoration).color!;
  }

  testWidgets('fills the given number of steps with the neutral text colour, one semantics node', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: Center(child: OmiLevelMeter(level: 2, semanticsLabel: 'Confidence: Likely'))),
    ));
    expect(stepColor(tester, 0), OmiColors.textPrimary);
    expect(stepColor(tester, 1), OmiColors.textPrimary);
    expect(stepColor(tester, 2), isNot(OmiColors.textPrimary));
    expect(find.bySemanticsLabel('Confidence: Likely'), findsOneWidget);
  });

  testWidgets('a step that fills while on screen animates in (the tick-up moment)', (tester) async {
    Widget meter(int level) => MaterialApp(
          home: Scaffold(body: Center(child: OmiLevelMeter(level: level, semanticsLabel: 'Confidence'))),
        );
    await tester.pumpWidget(meter(2));
    await tester.pumpWidget(meter(3));
    await tester.pump(const Duration(milliseconds: 50));
    final mid = tester.widget<DecoratedBox>(
      find.descendant(of: find.byKey(const ValueKey('omi_level_meter_step_2')), matching: find.byType(DecoratedBox)),
    );
    expect((mid.decoration as BoxDecoration).color, isNot(OmiColors.textPrimary));
    await tester.pumpAndSettle();
    expect(stepColor(tester, 2), OmiColors.textPrimary);
  });
}
