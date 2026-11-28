import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_words_merge.dart';

// Reliability experiment vendor_recognizer_on_opened_app: the phone's own recogniser comes first; the
// vendor's words show only for stretches of audio the phone's recogniser has nothing for.

final t0 = DateTime.utc(2026, 11, 25, 12);
DateTime at(double seconds) => t0.add(Duration(milliseconds: (seconds * 1000).round()));

LivePreviewLine own(String id, String text, double start, double end, {bool isFinal = true}) =>
    LivePreviewLine(id: id, text: text, isFinal: isFinal, startedAt: at(start), endedAt: at(end), firstSeenAt: at(end));

/// A vendor line whose words are spread evenly over [start]..[end].
LivePreviewLine vendor(String id, String text, double start, double end) {
  final words = text.split(' ');
  final step = (end - start) / words.length;
  return LivePreviewLine(
    id: id,
    text: text,
    isFinal: true,
    startedAt: at(start),
    endedAt: at(end),
    firstSeenAt: at(end + 5),
    spans: [
      for (var i = 0; i < words.length; i++)
        LivePreviewSpan(text: words[i], startedAt: at(start + i * step), endedAt: at(start + (i + 1) * step - 0.05)),
    ],
  );
}

List<String> texts(List<LivePreviewLine> lines) => [for (final line in lines) line.text];

void main() {
  test('without vendor lines the phone\'s own list is returned as it is', () {
    final lines = [own('a', 'hello there', 0, 2)];
    expect(identical(LiveWordsMerge.merge(lines, const []), lines), isTrue);
  });

  test('with no lines from the phone\'s recogniser every vendor line shows', () {
    final lines = [vendor('v1', 'one two three', 0, 3), vendor('v2', 'four five', 6, 8)];
    expect(texts(LiveWordsMerge.merge(const [], lines)), ['one two three', 'four five']);
  });

  test('vendor words over the same audio as the phone\'s words never show twice', () {
    final merged = LiveWordsMerge.merge(
      [own('a', 'hello there how are you', 0, 4)],
      [vendor('v1', 'Hello there, how are you?', 0.2, 4.3)],
    );
    expect(texts(merged), ['hello there how are you']);
  });

  test('a stretch the phone\'s recogniser has nothing for shows the vendor words, in audio order', () {
    final merged = LiveWordsMerge.merge(
      [own('a', 'first sentence', 0, 2), own('b', 'third sentence', 20, 22)],
      [vendor('v1', 'First sentence.', 0, 2), vendor('v2', 'second one here', 9, 12), vendor('v3', 'Third.', 20, 21)],
    );
    expect(texts(merged), ['first sentence', 'second one here', 'third sentence']);
    expect(merged[1].id, 'v2');
    expect(merged[1].startedAt, at(9));
  });

  test('words within a second of the phone\'s line count as covered; later ones show', () {
    // The phone's recogniser stalls at 4.0 s. The vendor line runs on to 10 s.
    final merged = LiveWordsMerge.merge(
      [own('a', 'it was working', 0, 4)],
      [vendor('v1', 'a b c d e f g h i j', 0, 10)],
    );
    // Words that start up to 5.0 s (4.0 + tolerance) are the phone's; g..j are the vendor's.
    expect(texts(merged), ['it was working', 'g h i j']);
    expect(merged[1].id, 'v1#0');
    expect(merged[1].startedAt, at(6));
    expect(merged[1].spans, hasLength(4));
  });

  test('a vendor line the phone covers in the middle becomes two', () {
    final merged = LiveWordsMerge.merge(
      [own('a', 'middle', 9.5, 10.5)],
      [vendor('v1', 'a b c d e f g h i j k l m n o p q r s t', 0, 20)],
    );
    expect(texts(merged), ['a b c d e f g h', 'middle', 'm n o p q r s t']);
    expect([merged[0].id, merged[2].id], ['v1#0', 'v1#1']);
  });

  test('the phone\'s recogniser filling a stretch later drops the vendor words for it', () {
    final vendorLines = [vendor('v1', 'late words here', 9, 12)];
    expect(texts(LiveWordsMerge.merge([own('a', 'x', 0, 1)], vendorLines)), ['x', 'late words here']);
    final filled = [own('a', 'x', 0, 1), own('b', 'late words here', 9, 12, isFinal: false)];
    expect(texts(LiveWordsMerge.merge(filled, vendorLines)), ['x', 'late words here']);
    expect(LiveWordsMerge.merge(filled, vendorLines).map((line) => line.id), ['a', 'b']);
  });

  test('a line of the phone\'s recogniser without audio times covers the seconds before it was reported', () {
    final untimed = LivePreviewLine(id: 'a', text: 'no times', isFinal: true, firstSeenAt: at(10));
    final merged = LiveWordsMerge.merge([untimed], [vendor('v1', 'covered', 5, 6), vendor('v2', 'after', 14, 15)]);
    expect(texts(merged), ['no times', 'after']);
  });

  test('an empty line of the phone\'s recogniser covers nothing', () {
    final merged = LiveWordsMerge.merge([own('a', '  ', 0, 10)], [vendor('v1', 'heard', 2, 3)]);
    expect(texts(merged), ['  ', 'heard']);
  });
}
