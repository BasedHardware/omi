import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/episodes/start_trimmed_text.dart';

void main() {
  const style = TextStyle(fontSize: 14);
  for (final unit in ['日本語の最新情報', '最新中文内容', '👩🏽‍💻', 'ที่', '𠀀𠀁']) {
    for (final maxLines in [1, 3]) {
      testWidgets('keeps the newest $unit graphemes in $maxLines lines', (tester) async {
        // Exceeds the measurement cap too, including UTF-16 surrogate pairs,
        // combining marks and emoji joined by ZWJ.
        final full = List.filled(180, unit).join();
        await tester.pumpWidget(MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 140,
                child: StartTrimmedText(
                  runs: [(text: full, style: null)],
                  style: style,
                  maxLines: maxLines,
                ),
              ),
            ),
          ),
        ));
        final text = tester.widget<Text>(find.byType(Text));
        final span = text.textSpan!;
        final displayed = span.toPlainText();
        expect(displayed, startsWith('…'));
        final tail = displayed.substring(1);
        expect(tail, isNotEmpty);
        expect(full, endsWith(tail));
        expect(full.characters.skip(full.characters.length - tail.characters.length).join(), tail,
            reason: 'the cut must be at a complete grapheme');
        final painter = TextPainter(text: span, maxLines: maxLines, textDirection: TextDirection.ltr)
          ..layout(maxWidth: 140);
        expect(painter.didExceedMaxLines, isFalse, reason: 'end ellipsis must never hide the newest text');
        painter.dispose();
        expect(tester.takeException(), isNull);
      });
    }
  }

  testWidgets('falls back within an oversized last word and retains the tail style', (tester) async {
    const tailStyle = TextStyle(color: Colors.grey);
    final tail = List.filled(90, 'かな').join();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 140,
          child: StartTrimmedText(
            runs: [(text: 'older words ', style: null), (text: tail, style: tailStyle)],
            style: style,
          ),
        ),
      ),
    ));
    final span = tester.widget<Text>(find.byType(Text)).textSpan! as TextSpan;
    expect(span.toPlainText(), startsWith('…'));
    expect(span.toPlainText(), isNot(contains('older')));
    expect(span.children!.last.style, tailStyle);
    expect(tail, endsWith(span.toPlainText().substring(1)));
  });

  testWidgets('text that fits retains its full text and no leading ellipsis', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: StartTrimmedText(runs: [(text: '最新 words', style: null)], style: style)),
    ));
    expect(tester.widget<Text>(find.byType(Text)).textSpan!.toPlainText(), '最新 words');
  });
}
