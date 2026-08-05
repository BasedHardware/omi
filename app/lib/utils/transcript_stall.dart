// Live transcript stall helpers for BLE device capture (#6977).
// Pure predicates so the "zombie Listening" contract can be unit-tested
// without spinning up CaptureController / sockets.

/// Default: surface a stall warning after this much silence in transcript progress.
///
/// This is silence in *transcript output*, not audio input — a person pausing
/// mid-conversation, listening rather than speaking, or a quiet room are all
/// completely normal and can easily exceed 15s without any transcript segment
/// arriving. 15s made the watchdog restart healthy sockets during ordinary
/// pauses (cubic review on #6977). Raised well past typical conversational
/// pause lengths while staying far short of "the session went dead for
/// minutes" territory this watchdog exists to catch.
const Duration kTranscriptStallWarningAfter = Duration(seconds: 45);

/// WAL frames may be marked synced after a local socket send only while transcript
/// progress has advanced within this grace window.
const Duration kFrameSyncedGraceAfterTranscriptProgress = Duration(seconds: 10);

const Duration kTranscriptStallWatchdogTick = Duration(seconds: 5);

/// Whether the capture UI should leave the indefinite "Listening" state.
bool shouldReportTranscriptStall({
  required bool transcriptServiceReady,
  required bool isDeviceRecording,
  required bool isPaused,
  required bool hasTerminalTranscriptionFailure,
  required bool hasTranscriptSegments,
  required bool hasSeenTranscriptProgress,
  required int secondsSinceLastTranscriptProgress,
  Duration stallAfter = kTranscriptStallWarningAfter,
}) {
  if (!transcriptServiceReady) return false;
  if (!isDeviceRecording) return false;
  if (isPaused) return false;
  if (hasTerminalTranscriptionFailure) return false;
  if (!hasTranscriptSegments) return false;
  if (!hasSeenTranscriptProgress) return false;
  return secondsSinceLastTranscriptProgress >= stallAfter.inSeconds;
}

/// Seconds of stall silence after one watchdog tick (or 0 when monitoring is inactive).
int nextSecondsSinceTranscriptProgress({
  required bool monitoringActive,
  required int previousSeconds,
  Duration tick = kTranscriptStallWatchdogTick,
}) {
  if (!monitoringActive) return 0;
  return previousSeconds + tick.inSeconds;
}

/// Whether a successful local websocket send is durable enough to mark WAL frames synced.
bool shouldMarkFramesSyncedAfterSocketSend({
  required bool walSupported,
  required bool transcriptServiceReady,
  required DateTime? lastTranscriptProgressAt,
  required DateTime now,
  Duration grace = kFrameSyncedGraceAfterTranscriptProgress,
}) {
  if (!walSupported || !transcriptServiceReady) return false;
  final last = lastTranscriptProgressAt;
  if (last == null) return false;
  return now.difference(last) <= grace;
}

/// Keep "reconnecting" visible across an intentional watchdog socket restart.
///
/// When the watchdog calls `stop()`, `onClosed` fires immediately. Clearing the
/// stall flag there would flash Listening again before reconnect completes.
bool shouldPreserveTranscriptStallAcrossSocketClose({
  required bool stallRestartInFlight,
}) =>
    stallRestartInFlight;
