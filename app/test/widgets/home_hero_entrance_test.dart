import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/home/widgets/home_hero.dart';

/// The hero fades in, so its headline is only the colour it declares once the
/// entrance has finished. A screenshot caught it at ~75% opacity, which is
/// indistinguishable from "the text is grey" — these pin the end state.
void main() {
  Future<void> pumpHero(WidgetTester tester, {required bool animate}) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: Center(child: HomeHero(animate: animate))),
      ),
    );
  }

  double heroOpacity(WidgetTester tester) {
    final opacities = tester.widgetList<Opacity>(find.byType(Opacity)).toList();
    expect(opacities, isNotEmpty, reason: 'the hero wraps its content in an entrance Opacity');
    return opacities.first.opacity;
  }

  testWidgets('the entrance settles fully opaque', (tester) async {
    await pumpHero(tester, animate: true);

    // Mid-flight it is deliberately partial.
    await tester.pump(const Duration(milliseconds: 300));
    expect(heroOpacity(tester), lessThan(1.0));

    await tester.pumpAndSettle();
    expect(heroOpacity(tester), 1.0, reason: 'a headline left below 1.0 renders grey, not white');
  });

  testWidgets('with animate off it is opaque on the first frame', (tester) async {
    await pumpHero(tester, animate: false);
    await tester.pump();

    expect(heroOpacity(tester), 1.0);
  });

  testWidgets('the headline declares pure white', (tester) async {
    await pumpHero(tester, animate: false);
    await tester.pump();

    final text = tester.widget<Text>(find.text('Ask Omi anything about your life'));
    expect(text.style?.color, Colors.white);
  });
}
