import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/conversations/widgets/processing_capture.dart';

void main() {
  Future<void> pump(WidgetTester tester, String text) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          backgroundColor: Colors.black,
          body: Center(child: SizedBox(width: 200, child: LiveTranscriptPreview(text: text))),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('keeps the newest words in view as the line grows', (tester) async {
    // Recognition grows one segment, so the words that matter are the ones at
    // the end. Assert where the line actually sits, not just which flags are
    // set: the tail has to be against the trailing edge and the head off view.
    await pump(tester, 'To make it feel like you had already been there');
    var viewport = tester.getRect(find.byType(SingleChildScrollView));
    var line = tester.getRect(find.byType(Text));
    expect(line.right, moreOrLessEquals(viewport.right, epsilon: 0.5));
    expect(line.left, lessThan(viewport.left), reason: 'the older words scroll off, not the newer ones');

    // The same segment keeps growing — the view has to follow it.
    await pump(tester, 'To make it feel like you had already been there before you ever walked in');
    viewport = tester.getRect(find.byType(SingleChildScrollView));
    line = tester.getRect(find.byType(Text));
    expect(line.right, moreOrLessEquals(viewport.right, epsilon: 0.5));
    expect(line.width, greaterThan(viewport.width));

    expect(
      tester.widget<Text>(find.byType(Text)).overflow,
      isNot(TextOverflow.ellipsis),
      reason: 'an ellipsis would cut exactly the words just spoken',
    );
  });

  testWidgets('leaves a short line against the left edge', (tester) async {
    await pump(tester, 'hello');

    // The text box is stretched to the viewport, so the line reads from the
    // left instead of being pushed against the trailing edge.
    expect(tester.getSize(find.byType(Text)).width, 200);
  });
}
