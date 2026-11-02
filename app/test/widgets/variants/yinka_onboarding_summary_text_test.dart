import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/onboarding/variants/yinka/activation/activation_motion.dart';

// Omi's notes arrive as markdown; the onboarding card shows them as clean text and never grows
// past its box, however long the notes are.

const _realNotes = '''## Lunch Update on Sam

- One speaker mentioned having lunch with Sam, noting that she plans to move to Lisbon in June.

## Action Item Reminders

- A speaker requested reminders to **send the deck** to their team by Friday and to pick up milk on the way.''';

void main() {
  test('markdown becomes headings, bullets and plain text', () {
    final lines = summaryLines(_realNotes);
    expect(lines.map((l) => l.text), [
      'Lunch Update on Sam',
      'One speaker mentioned having lunch with Sam, noting that she plans to move to Lisbon in June.',
      'Action Item Reminders',
      'A speaker requested reminders to send the deck to their team by Friday and to pick up milk on the way.',
    ]);
    expect(lines.map((l) => l.heading), [true, false, true, false]);
    expect(lines.map((l) => l.bullet), [false, true, false, true]);
  });

  test('plain prose stays one line', () {
    final lines = summaryLines('Lunch with Sam, who is moving to Lisbon in June.');
    expect(lines, hasLength(1));
    expect(lines.single.heading || lines.single.bullet, isFalse);
  });

  testWidgets('long notes stay inside the box and show no markdown', (tester) async {
    tester.view.physicalSize = const Size(402 * 3, 874 * 3);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    final long = List.filled(4, _realNotes).join('\n\n');
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: Center(child: SummaryText(text: long, t: 1, style: const TextStyle(fontSize: 17)))),
    ));
    expect(tester.takeException(), isNull);
    expect(tester.getSize(find.byType(SummaryText)).height, lessThanOrEqualTo(190));
    expect(find.textContaining('##', findRichText: true), findsNothing);
    expect(find.textContaining('**', findRichText: true), findsNothing);
  });
}
