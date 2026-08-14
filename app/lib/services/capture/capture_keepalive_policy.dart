import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/enums.dart';

/// Window after reconnect in which an audio CCCD notification must arrive
/// before the GATT link is treated as a dead capture path.
const captureAudioLivenessWindow = Duration(seconds: 4);

/// One CCCD re-subscribe is allowed when the liveness window expires silent.
const captureAudioSilenceResubscribeLimit = 1;

/// STT keep-alive may reconnect the websocket only if audio bytes arrived
/// within this window. Matches the existing 15s keep-alive period.
const captureKeepAliveRecentAudioWindow = Duration(seconds: 15);

/// After entering a live recording state, hold the iOS audio/FGS keep-alive
/// this long even before the first frame so startup is not a flap.
const captureForegroundStartGrace = Duration(seconds: 5);

/// Audio is stale (stop treating the path as live capture) after this silence.
const captureForegroundAudioStaleAfter = Duration(seconds: 5);

/// Location permission alone must never start `flutter_foreground_task`.
/// On iOS that plugin holds AVAudioSession (green mic indicator) all day.
bool shouldStartForegroundTaskFromLocationPermission() => false;

bool isBleAudioCharacteristicUuid(String characteristicUuid) {
  final c = characteristicUuid.toLowerCase();
  return c == audioDataStreamCharacteristicUuid.toLowerCase() ||
      c == friendPendantAudioCharacteristicUuid.toLowerCase() ||
      c == limitlessRxCharUuid.toLowerCase() ||
      c == beeAudioCharacteristicUuid.toLowerCase() ||
      c == fieldyAudioCharacteristicUuid.toLowerCase() ||
      c == plaudNotifyCharUuid.toLowerCase();
}

bool isLiveCaptureRecordingState(RecordingState state) {
  return state == RecordingState.record ||
      state == RecordingState.deviceRecord ||
      state == RecordingState.systemAudioRecord;
}

/// Phone-mic (`record`) and system-audio own AVAudioSession for the whole
/// session, including Transcribe Later batch (no Dart frames). Wearable
/// `deviceRecord` is the BLE path that may configure-and-deactivate Bluetooth.
bool isSessionLongCaptureForegroundState(RecordingState state) {
  return state == RecordingState.record || state == RecordingState.systemAudioRecord;
}

bool isBluetoothCaptureForegroundOwner(RecordingState state) {
  return state == RecordingState.deviceRecord;
}

/// Hold flutter_foreground_task / iOS audio session only while capture is
/// actually running and audio is flowing (or still within startup grace).
///
/// Phone-mic and system-audio own the session for the whole recording — a
/// talk gap must not flap FGS or deactivate AVAudioSession under them.
/// Wearable `deviceRecord` holds during startup grace or while frames flow.
bool shouldHoldCaptureForegroundTask({
  required RecordingState recordingState,
  required DateTime? lastAudioFrameAt,
  required DateTime? recordingStartedAt,
  required DateTime now,
}) {
  if (!isLiveCaptureRecordingState(recordingState)) {
    return false;
  }
  if (isSessionLongCaptureForegroundState(recordingState)) {
    return true;
  }
  if (recordingStartedAt != null && now.difference(recordingStartedAt) <= captureForegroundStartGrace) {
    return true;
  }
  if (lastAudioFrameAt == null) {
    return false;
  }
  return now.difference(lastAudioFrameAt) <= captureForegroundAudioStaleAfter;
}

/// After wearable FGS is released for stale audio, a new frame must re-sync
/// or the keep-alive stays off for the rest of the session.
bool shouldResyncCaptureForegroundOnAudioFrame({
  required bool currentlyHeld,
  required RecordingState recordingState,
}) {
  return !currentlyHeld && isLiveCaptureRecordingState(recordingState);
}

/// Drop the previous session's last-frame timestamp when entering or leaving
/// live capture so a new/stopped session cannot inherit a 15s keep-alive hit.
bool shouldClearCaptureAudioTimestamp({
  required bool wasLive,
  required bool isLive,
}) {
  return !isLive || !wasLive;
}

/// Whether the 15s STT keep-alive should open a new websocket.
bool shouldReconnectSttKeepAlive({
  required bool recordingDeviceServiceReady,
  required bool socketConnected,
  required bool signedIn,
  required bool hasRecordingDevice,
  required bool isPhoneMicKeepAliveState,
  required DateTime? lastAudioFrameAt,
  required DateTime now,
}) {
  if (!recordingDeviceServiceReady || socketConnected || !signedIn) {
    return false;
  }
  if (!hasRecordingDevice && !isPhoneMicKeepAliveState) {
    return false;
  }
  if (lastAudioFrameAt == null) {
    return false;
  }
  return now.difference(lastAudioFrameAt) <= captureKeepAliveRecentAudioWindow;
}
