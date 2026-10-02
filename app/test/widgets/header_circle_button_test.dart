import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/widgets/header_circle_button.dart';

void main() {
  Future<int Function()> pumpButton(WidgetTester tester, {double diameter = kHeaderCircleDiameter}) async {
    var taps = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: HeaderCircleButton(
              icon: const Icon(Icons.settings, size: 16),
              semanticLabel: 'Settings',
              diameter: diameter,
              onTap: () => taps++,
            ),
          ),
        ),
      ),
    );
    return () => taps;
  }

  testWidgets('owns a 44pt touch target around the smaller circle it paints', (tester) async {
    // Apple HIG: hit targets of at least 44x44pt. The painted circle stays
    // smaller; the target around it is what grew.
    for (final diameter in [36.0, 32.0]) {
      final taps = await pumpButton(tester, diameter: diameter);

      final target = tester.getRect(find.byType(HeaderCircleButton));
      expect(target.size, const Size(kMinTapTarget, kMinTapTarget));

      final circle = tester.getRect(
        find.descendant(of: find.byType(HeaderCircleButton), matching: find.byType(Container)),
      );
      expect(circle.size, Size(diameter, diameter));
      expect(circle.center, target.center);

      // A touch that lands outside the painted circle but inside the target —
      // the near miss the old 36pt target dropped — still counts.
      await tester.tapAt(target.centerLeft + const Offset(1, 0));
      await tester.tapAt(target.bottomCenter - const Offset(0, 1));
      expect(taps(), 2, reason: 'a ${diameter}pt circle should still take taps across the full target');
    }
  });

  testWidgets('announces its label and stays activatable, since it has no visible text', (tester) async {
    final semantics = tester.ensureSemantics();
    await pumpButton(tester);

    final data = tester.getSemantics(find.bySemanticsLabel('Settings')).getSemanticsData();
    expect(data.flagsCollection.isButton, isTrue);
    expect(data.hasAction(SemanticsAction.tap), isTrue, reason: 'a screen reader must be able to activate it');
    semantics.dispose();
  });
}
