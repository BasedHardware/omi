import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/transcript_stall.dart';

void main() {
  group('shouldReportTranscriptStall (#6977)', () {
    test('reports stall only after sustained silence during live device capture', () {
      expect(
        shouldReportTranscriptStall(
          transcriptServiceReady: true,
          isDeviceRecording: true,
          isPaused: false,
          hasTerminalTranscriptionFailure: false,
          hasTranscriptSegments: true,
          hasSeenTranscriptProgress: true,
          secondsSinceLastTranscriptProgress: 15,
        ),
        isTrue,
      );
    });

    test('does not report stall before the warning threshold', () {
      expect(
        shouldReportTranscriptStall(
          transcriptServiceReady: true,
          isDeviceRecording: true,
          isPaused: false,
          hasTerminalTranscriptionFailure: false,
          hasTranscriptSegments: true,
          hasSeenTranscriptProgress: true,
          secondsSinceLastTranscriptProgress: 10,
        ),
        isFalse,
      );
    });

    test('does not report stall when paused, not ready, or no prior progress', () {
      expect(
        shouldReportTranscriptStall(
          transcriptServiceReady: true,
          isDeviceRecording: true,
          isPaused: true,
          hasTerminalTranscriptionFailure: false,
          hasTranscriptSegments: true,
          hasSeenTranscriptProgress: true,
          secondsSinceLastTranscriptProgress: 30,
        ),
        isFalse,
      );
      expect(
        shouldReportTranscriptStall(
          transcriptServiceReady: false,
          isDeviceRecording: true,
          isPaused: false,
          hasTerminalTranscriptionFailure: false,
          hasTranscriptSegments: true,
          hasSeenTranscriptProgress: true,
          secondsSinceLastTranscriptProgress: 30,
        ),
        isFalse,
      );
      expect(
        shouldReportTranscriptStall(
          transcriptServiceReady: true,
          isDeviceRecording: true,
          isPaused: false,
          hasTerminalTranscriptionFailure: false,
          hasTranscriptSegments: true,
          hasSeenTranscriptProgress: false,
          secondsSinceLastTranscriptProgress: 30,
        ),
        isFalse,
      );
    });
  });

  group('shouldMarkFramesSyncedAfterSocketSend (#6977)', () {
    final now = DateTime.utc(2026, 8, 5, 12);

    test('allows synced marks only while transcript progress is recent', () {
      expect(
        shouldMarkFramesSyncedAfterSocketSend(
          walSupported: true,
          transcriptServiceReady: true,
          lastTranscriptProgressAt: now.subtract(const Duration(seconds: 5)),
          now: now,
        ),
        isTrue,
      );
      expect(
        shouldMarkFramesSyncedAfterSocketSend(
          walSupported: true,
          transcriptServiceReady: true,
          lastTranscriptProgressAt: now.subtract(const Duration(seconds: 20)),
          now: now,
        ),
        isFalse,
      );
    });

    test('never marks synced when WAL or transcript service is inactive', () {
      expect(
        shouldMarkFramesSyncedAfterSocketSend(
          walSupported: false,
          transcriptServiceReady: true,
          lastTranscriptProgressAt: now,
          now: now,
        ),
        isFalse,
      );
      expect(
        shouldMarkFramesSyncedAfterSocketSend(
          walSupported: true,
          transcriptServiceReady: false,
          lastTranscriptProgressAt: now,
          now: now,
        ),
        isFalse,
      );
    });
  });

  group('nextSecondsSinceTranscriptProgress', () {
    test('accumulates ticks while monitoring and resets when inactive', () {
      expect(nextSecondsSinceTranscriptProgress(monitoringActive: true, previousSeconds: 10), 15);
      expect(nextSecondsSinceTranscriptProgress(monitoringActive: false, previousSeconds: 10), 0);
    });
  });
}
