/// Pause/mute contract for the CV1 pendant (issue #5054).
///
/// The pendant is the source of truth. BLE disconnect must not resume capture.
/// Only an explicit unmute resumes it.
class DeviceMuteSync {
  /// Firmware pusher policy: a muted device must not TX or store audio,
  /// whether or not a phone is connected. Connection state is not a parameter
  /// because it must not be able to resume capture.
  static bool firmwareShouldCapture({required bool muted}) => !muted;

  /// Reconnect UI: device mute wins. A missing characteristic (old firmware
  /// or a failed read) falls back to the app's persisted mute.
  static bool resolveReconnectPaused({required bool? deviceMuted, required bool localMuted}) {
    return deviceMuted ?? localMuted;
  }
}
