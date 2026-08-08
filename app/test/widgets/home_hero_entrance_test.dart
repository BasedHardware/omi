import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/home/widgets/home_hero.dart';

/// The hero fades in, so the headline is only the colour it declares once the
/// entrance has finished — and only if nothing is left compositing over it.
///
/// Both mattered in practice: a screenshot caught it mid-fade at ~75%, and the
/// settled frame still rendered a few percent short of white because the
/// entrance's Opacity layer stayed in the tree at opacity 1.0.
void main() {
  Future<void> pumpHero(WidgetTester tester, {required bool animate}) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: Center(child: HomeHero(animate: animate))),
      ),
    );
  }

  testWidgets('the entrance fades in, then leaves nothing compositing over the text', (tester) async {
    await pumpHero(tester, animate: true);

    await tester.pump(const Duration(milliseconds: 300));
    final midFlight = tester.widgetList<Opacity>(find.byType(Opacity)).toList();
    expect(midFlight, isNotEmpty, reason: 'mid-flight it fades');
    expect(midFlight.first.opacity, lessThan(1.0));

    await tester.pumpAndSettle();

    // Not "opacity == 1.0" — the layer must be gone. An Opacity at 1.0 still
    // round-trips the text through an offscreen buffer, which is what rendered
    // the headline grey on device.
    expect(
      find.byType(Opacity),
      findsNothing,
      reason: 'a settled hero must not composite its text through an opacity layer',
    );
  });

  testWidgets('with animate off there is no opacity layer at all', (tester) async {
    await pumpHero(tester, animate: false);
    await tester.pump();

    expect(find.byType(Opacity), findsNothing);
  });

  testWidgets('the headline declares pure white', (tester) async {
    await pumpHero(tester, animate: false);
    await tester.pump();

    final text = tester.widget<Text>(find.text('Ask Omi anything about your life'));
    expect(text.style?.color, Colors.white);
  });
}
