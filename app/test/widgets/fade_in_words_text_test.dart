import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/widgets/fade_in_words_text.dart';

void main() {
  Widget host(String text) => MaterialApp(
        home: Scaffold(
          body: FadeInWordsText(
            text: text,
            wordDuration: const Duration(milliseconds: 100),
            stagger: const Duration(milliseconds: 50),
          ),
        ),
      );

  double opacityOf(WidgetTester tester, String word) {
    final finder = find.ancestor(of: find.text(word), matching: find.byType(AnimatedOpacity));
    return tester.widget<AnimatedOpacity>(finder).opacity;
  }

  testWidgets('new words start transparent and fade in one after another', (tester) async {
    await tester.pumpWidget(host('hello world'));

    // First frame: nothing revealed yet.
    expect(opacityOf(tester, 'hello'), 0.0);
    expect(opacityOf(tester, 'world'), 0.0);

    await tester.pump(Duration.zero); // zero-delay timer reveals the first word
    expect(opacityOf(tester, 'hello'), 1.0);
    expect(opacityOf(tester, 'world'), 0.0, reason: 'second word waits for its stagger delay');

    await tester.pump(const Duration(milliseconds: 60));
    expect(opacityOf(tester, 'world'), 1.0);

    await tester.pumpAndSettle();
  });

  testWidgets('appending words only animates the appended ones', (tester) async {
    await tester.pumpWidget(host('hello world'));
    await tester.pumpAndSettle();
    expect(opacityOf(tester, 'hello'), 1.0);
    expect(opacityOf(tester, 'world'), 1.0);

    await tester.pumpWidget(host('hello world again'));
    expect(opacityOf(tester, 'hello'), 1.0, reason: 'existing words must not flicker');
    expect(opacityOf(tester, 'world'), 1.0);
    expect(opacityOf(tester, 'again'), 0.0);

    await tester.pumpAndSettle();
    expect(opacityOf(tester, 'again'), 1.0);
  });

  testWidgets('a rewritten transcript reveals everything again', (tester) async {
    await tester.pumpWidget(host('hello world'));
    await tester.pumpAndSettle();

    await tester.pumpWidget(host('brand new'));
    expect(opacityOf(tester, 'brand'), 0.0);
    expect(opacityOf(tester, 'new'), 0.0);
    expect(find.text('hello'), findsNothing);

    await tester.pumpAndSettle();
    expect(opacityOf(tester, 'brand'), 1.0);
    expect(opacityOf(tester, 'new'), 1.0);
  });

  testWidgets('renders nothing for an empty transcript', (tester) async {
    await tester.pumpWidget(host('   '));
    expect(find.byType(AnimatedOpacity), findsNothing);
  });
}
