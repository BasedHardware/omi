import 'package:flutter/material.dart';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/widgets/footer_glass.dart';
import 'package:omi/widgets/top_bar_glass.dart';

/// The experimental design's press rule: a control grows by its height's share; in a shared
/// capsule only the pressed button grows.
void main() {
  test('smaller controls grow by a larger share, within the cap', () {
    expect(GlassStyle.pressScale(56), closeTo(1.0625, 0.001));
    expect(GlassStyle.pressScale(40), greaterThan(GlassStyle.pressScale(56)));
    expect(GlassStyle.pressScale(34), greaterThan(GlassStyle.pressScale(40)));
    expect(GlassStyle.pressScale(10), 1.12);
    // The shadow follows the height too.
    expect(GlassStyle.shadow(36, dark: false).blurRadius, lessThan(GlassStyle.shadow(56, dark: false).blurRadius));
  });

  double scaleAround(WidgetTester tester, Finder finder) {
    final scales =
        tester.widgetList<AnimatedScale>(find.ancestor(of: finder, matching: find.byType(AnimatedScale))).toList();
    return scales.fold<double>(1, (total, widget) => total * widget.scale);
  }

  testWidgets('pressing one button of a capsule grows that button only', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: TopBarGlass(
              children: [
                for (final name in ['a', 'b', 'c'])
                  SizedBox(key: Key(name), width: 44, height: 44, child: const Icon(Icons.star)),
              ],
            ),
          ),
        ),
      ),
    );
    final capsule = tester.getSize(find.byType(TopBarGlass));
    expect(capsule.width, 3 * 44 + 4);

    final gesture = await tester.startGesture(tester.getCenter(find.byKey(const Key('b'))));
    await tester.pumpAndSettle();
    expect(scaleAround(tester, find.byKey(const Key('b'))), GlassStyle.itemPressScale);
    expect(scaleAround(tester, find.byKey(const Key('a'))), 1);
    expect(scaleAround(tester, find.byKey(const Key('c'))), 1);
    // The capsule itself has not moved or grown.
    expect(scaleAround(tester, find.byType(FooterGlassSurface)), 1);

    await gesture.up();
    await tester.pumpAndSettle();
    expect(scaleAround(tester, find.byKey(const Key('b'))), 1);
  });

  testWidgets('a single button grows as a whole, by the rule for its height', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Center(
            child: TopBarGlass(children: [SizedBox(key: Key('back'), width: 44, height: 44)]),
          ),
        ),
      ),
    );
    final gesture = await tester.startGesture(tester.getCenter(find.byKey(const Key('back'))));
    await tester.pumpAndSettle();
    expect(scaleAround(tester, find.byKey(const Key('back'))), GlassStyle.pressScale(40));
    await gesture.up();
    await tester.pumpAndSettle();
  });
}
