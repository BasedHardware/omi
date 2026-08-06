import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/live_transcript_preview.dart';

void main() {
  test('an empty reconnect snapshot cannot erase the visible preview', () {
    final current = [_segment('socket-a', 0, 2, 'before disconnect')];

    final merged = LiveTranscriptPreview.reconcile(
      current: current,
      serverSnapshot: const [],
    );

    expect(merged.map((segment) => segment.id), ['socket-a']);
    expect(merged, isNot(same(current)));
  });

  test('a stale snapshot updates known segments and keeps newer socket data', () {
    final current = [
      _segment('shared', 0, 2, 'interim'),
      _segment('socket-new', 2, 4, 'after reconnect'),
    ];

    final merged = LiveTranscriptPreview.reconcile(
      current: current,
      serverSnapshot: [
        _segment('shared', 0, 2.5, 'final'),
        _segment('server-middle', 1.5, 2, 'persisted'),
      ],
    );

    expect(
      merged.map((segment) => segment.id),
      ['shared', 'server-middle', 'socket-new'],
    );
    expect(merged.first.text, 'final');
  });
}

TranscriptSegment _segment(
  String id,
  double start,
  double end,
  String text,
) =>
    TranscriptSegment(
      id: id,
      text: text,
      speaker: 'SPEAKER_00',
      isUser: false,
      personId: null,
      start: start,
      end: end,
      translations: const [],
    );
