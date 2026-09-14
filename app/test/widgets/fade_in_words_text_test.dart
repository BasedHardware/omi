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

  testWidgets('visibleLines keeps only the last whole lines', (tester) async {
    // 120px wide at 20px/word-ish: 'w0' .. 'w11' wrap onto several lines.
    Widget narrow(String text) => MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 120,
                child: FadeInWordsText(
                  text: text,
                  visibleLines: 3,
                  style: const TextStyle(fontSize: 20),
                  wordDuration: Duration.zero,
                  stagger: Duration.zero,
                ),
              ),
            ),
          ),
        );

    final words = List.generate(12, (i) => 'w$i');
    await tester.pumpWidget(narrow(words.take(4).join(' ')));
    await tester.pumpAndSettle();
    expect(find.text('w0'), findsOneWidget, reason: 'short text shows everything');

    await tester.pumpWidget(narrow(words.join(' ')));
    await tester.pumpAndSettle();
    expect(find.text('w0'), findsNothing, reason: 'earlier lines drop off whole');
    expect(find.text('w11'), findsOneWidget);

    // The words still shown never exceed three Wrap lines.
    final wrap = tester.widget<Wrap>(find.byType(Wrap));
    final shown = wrap.children.length;
    final firstShown = 12 - shown;
    final start = FadeInWordsText.firstVisibleWord(
      words: words,
      style: const TextStyle(fontSize: 20),
      gap: 6,
      maxWidth: 120,
      visibleLines: 3,
      textScaler: TextScaler.noScaling,
      textDirection: TextDirection.ltr,
    );
    expect(firstShown, start);
    expect(start, greaterThan(0));
  });
}
