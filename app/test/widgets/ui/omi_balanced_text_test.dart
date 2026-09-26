// OmiBalancedText: even lines instead of one word alone on the last line, and the height of the
// tallest copy a card can show, so a card keeps its height when its copy changes with state.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/components/omi_balanced_text.dart';

void main() {
  // The test font draws every glyph (and space) as a square as wide as the font size.
  const style = TextStyle(fontSize: 10, height: 1);

  Future<void> pumpIn(WidgetTester tester, Widget child, {double width = 200}) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Align(
          alignment: Alignment.topLeft,
          child: SizedBox(width: width, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [child])),
        ),
      ),
    ));
  }

  testWidgets('a lone last word is pulled up: the lines come out even', (tester) async {
    // 24 glyphs in 200 px (20 per line): "aaaa bbbb cccc dddd" then "eeee" alone.
    await pumpIn(tester, const OmiBalancedText('aaaa bbbb cccc dddd eeee', style: style));
    final text = tester.getSize(find.byType(Text));
    expect(text.height, 20, reason: 'still two lines');
    expect(text.width, lessThanOrEqualTo(150), reason: '"aaaa bbbb cccc" / "dddd eeee", not a lone "eeee"');
  });

  testWidgets('one line stays one line, at full width', (tester) async {
    await pumpIn(tester, const OmiBalancedText('aaaa bbbb', style: style));
    expect(tester.getSize(find.byType(Text)).height, 10);
  });

  testWidgets('holds the height of the tallest copy it can show', (tester) async {
    const long = 'aaaa bbbb cccc dddd eeee ffff gggg hhhh';
    await pumpIn(tester, const OmiBalancedText('Ready', style: style, reserveFor: [long, 'Ready']));
    final short = tester.getSize(find.byType(OmiBalancedText)).height;
    await pumpIn(tester, const OmiBalancedText(long, style: style, reserveFor: [long, 'Ready']));
    expect(tester.getSize(find.byType(OmiBalancedText)).height, short);
    expect(short, 20);
  });

  testWidgets('minLines holds that many lines', (tester) async {
    await pumpIn(tester, const OmiBalancedText('Ready', style: style, minLines: 2));
    expect(tester.getSize(find.byType(OmiBalancedText)).height, 20);
  });
}
