import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/conversation_capture_window.dart';

void main() {
  test('anchors recovered audio to the actual transcript span, not socket age', () {
    final window = ConversationCaptureWindow.fromTranscript(
      sessionOriginSeconds: 1000,
      fallbackStartSeconds: 1000,
      fallbackEndSeconds: 5000,
      segments: [
        _segment(start: 2400.5, end: 2410.2),
        _segment(start: 2500.1, end: 2510.8),
      ],
    );

    expect(window.startSeconds, 3398);
    expect(window.endSeconds, 3513);
  });

  test('uses the durable session bounds when no transcript is available', () {
    final window = ConversationCaptureWindow.fromTranscript(
      sessionOriginSeconds: 1000,
      fallbackStartSeconds: 900,
      fallbackEndSeconds: 1200,
      segments: const [],
    );

    expect(window.startSeconds, 900);
    expect(window.endSeconds, 1200);
  });

  test('requires non-empty timed transcript text as server speech proof', () {
    expect(
      ConversationCaptureWindow.hasServerSpeechProof([
        _segment(start: 0, end: 1, text: '   '),
        _segment(start: 1, end: 1, text: 'click'),
      ]),
      isFalse,
    );
    expect(
      ConversationCaptureWindow.hasServerSpeechProof([
        _segment(start: 1, end: 2, text: 'spoken words'),
      ]),
      isTrue,
    );
  });
}

TranscriptSegment _segment({
  required double start,
  required double end,
  String text = 'speech',
}) =>
    TranscriptSegment(
      id: '',
      text: text,
      speaker: 'SPEAKER_00',
      isUser: false,
      personId: null,
      start: start,
      end: end,
      translations: const [],
    );
