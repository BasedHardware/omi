import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/sockets/pure_streaming_stt.dart';

void main() {
  group('SttAudioTimeline', () {
    // 16 kHz, 16-bit mono: one second of audio is 32000 bytes.
    const oneSecond = 16000 * 2;

    test('stamps a delta with the audio consumed since the previous one', () {
      final timeline = SttAudioTimeline(sampleRate: 16000);

      timeline.addPcm(oneSecond * 2);
      final first = timeline.nextSegment();
      expect(first.start, 0.0);
      expect(first.end, closeTo(2.0, 1e-9));

      timeline.addPcm(oneSecond);
      final second = timeline.nextSegment();
      expect(second.start, closeTo(2.0, 1e-9));
      expect(second.end, closeTo(3.0, 1e-9));
    });

    test('many deltas over a short utterance stay inside the audio actually sent', () {
      final timeline = SttAudioTimeline(sampleRate: 16000);
      timeline.addPcm(oneSecond * 3);

      // Gemini Live streams `inputTranscription` as partial deltas; ten of them
      // can describe the same three seconds of speech. The old fixed 3s stride
      // would have ended this utterance at 30s.
      var last = timeline.nextSegment();
      for (var i = 0; i < 9; i++) {
        last = timeline.nextSegment();
      }

      expect(last.end, closeTo(3.0, 1e-9));
      expect(timeline.audioSeconds, closeTo(3.0, 1e-9));
    });

    test('deltas tile the timeline without gaps or overlaps', () {
      final timeline = SttAudioTimeline(sampleRate: 16000);
      var previousEnd = 0.0;

      for (var i = 0; i < 5; i++) {
        timeline.addPcm(oneSecond);
        final bounds = timeline.nextSegment();
        expect(bounds.start, closeTo(previousEnd, 1e-9));
        expect(bounds.end, greaterThanOrEqualTo(bounds.start));
        previousEnd = bounds.end;
      }

      expect(previousEnd, closeTo(5.0, 1e-9));
    });

    test('a delta arriving before any new audio does not invent time', () {
      final timeline = SttAudioTimeline(sampleRate: 16000);
      timeline.addPcm(oneSecond);
      timeline.nextSegment();

      final correction = timeline.nextSegment();
      expect(correction.start, closeTo(1.0, 1e-9));
      expect(correction.end, closeTo(1.0, 1e-9));
    });

    test('ignores empty and malformed audio accounting', () {
      final timeline = SttAudioTimeline(sampleRate: 16000);
      timeline.addPcm(0);
      timeline.addPcm(-1);
      expect(timeline.audioSeconds, 0.0);

      final broken = SttAudioTimeline(sampleRate: 0);
      broken.addPcm(oneSecond);
      expect(broken.audioSeconds, 0.0);
      expect(broken.nextSegment().end, 0.0);
    });

    test('reset drops back to an empty timeline for a fresh session', () {
      final timeline = SttAudioTimeline(sampleRate: 16000);
      timeline.addPcm(oneSecond * 4);
      timeline.nextSegment();

      timeline.reset();
      expect(timeline.audioSeconds, 0.0);

      timeline.addPcm(oneSecond);
      final bounds = timeline.nextSegment();
      expect(bounds.start, 0.0);
      expect(bounds.end, closeTo(1.0, 1e-9));
    });

    test('honors a non-default sample rate', () {
      final timeline = SttAudioTimeline(sampleRate: 24000);
      timeline.addPcm(24000 * 2);
      expect(timeline.nextSegment().end, closeTo(1.0, 1e-9));
    });
  });
}
