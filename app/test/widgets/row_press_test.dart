import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/experiments/experimental_design.dart';
import 'package:omi/widgets/row_press.dart';

void main() {
  tearDown(() => ExperimentalDesign.debugOverride = null);

  Widget host({required VoidCallback onTap}) => MaterialApp(
        home: Scaffold(
          body: ListView(
            children: [
              GestureDetector(
                onTap: onTap,
                child: const RowPress(child: SizedBox(key: Key('row'), height: 60, width: double.infinity)),
              ),
              const SizedBox(height: 2000),
            ],
          ),
        ),
      );

  double scale(WidgetTester tester) => tester
      .widget<AnimatedScale>(find.ancestor(of: find.byKey(const Key('row')), matching: find.byType(AnimatedScale)))
      .scale;

  testWidgets('off outside the experimental design', (tester) async {
    ExperimentalDesign.debugOverride = false;
    await tester.pumpWidget(host(onTap: () {}));
    expect(find.byType(AnimatedScale), findsNothing);
  });

  testWidgets('a held touch presses the row and lifting releases it; the tap still lands', (tester) async {
    ExperimentalDesign.debugOverride = true;
    var taps = 0;
    await tester.pumpWidget(host(onTap: () => taps++));
    final gesture = await tester.startGesture(tester.getCenter(find.byKey(const Key('row'))));
    await tester.pump(const Duration(milliseconds: 10));
    expect(scale(tester), 1, reason: 'not before the wait');
    await tester.pump(RowPress.showDelay);
    expect(scale(tester), RowPress.pressedScale);
    await gesture.up();
    await tester.pump();
    expect(scale(tester), 1);
    expect(taps, 1);
    await tester.pumpAndSettle();
  });

  testWidgets('a quick tap still shows, briefly', (tester) async {
    ExperimentalDesign.debugOverride = true;
    await tester.pumpWidget(host(onTap: () {}));
    await tester.tap(find.byKey(const Key('row')));
    await tester.pump();
    expect(scale(tester), RowPress.pressedScale);
    await tester.pump(RowPress.tapHold);
    expect(scale(tester), 1);
    await tester.pumpAndSettle();
  });

  testWidgets('a touch that becomes a scroll does not press the row', (tester) async {
    ExperimentalDesign.debugOverride = true;
    await tester.pumpWidget(host(onTap: () {}));
    final gesture = await tester.startGesture(tester.getCenter(find.byKey(const Key('row'))));
    await gesture.moveBy(const Offset(0, -40));
    await tester.pump(RowPress.showDelay * 2);
    expect(scale(tester), 1);
    await gesture.up();
    await tester.pumpAndSettle();
    expect(scale(tester), 1);
  });
}
