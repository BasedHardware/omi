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

  testWidgets('follows the end of the line as words arrive', (tester) async {
    // Recognition grows one segment; an ellipsized line would keep showing the
    // words that arrived first and hide everything said since.
    await pump(tester, 'To make it feel like you had already been there before you ever walked in');

    final scrollView = tester.widget<SingleChildScrollView>(find.byType(SingleChildScrollView));
    expect(scrollView.reverse, isTrue);
    expect(scrollView.scrollDirection, Axis.horizontal);

    final line = tester.widget<Text>(find.byType(Text));
    expect(line.overflow, isNot(TextOverflow.ellipsis), reason: 'ellipsis would cut the newest words');
    expect(line.data, endsWith('you ever walked in'));
  });

  testWidgets('leaves a short line against the left edge', (tester) async {
    await pump(tester, 'hello');

    // The text box is stretched to the viewport, so the line reads from the
    // left instead of being pushed against the trailing edge.
    expect(tester.getSize(find.byType(Text)).width, 200);
  });
}
