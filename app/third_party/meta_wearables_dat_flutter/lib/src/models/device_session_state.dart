/// Lifecycle state of an underlying [DeviceSession].
///
/// Distinct from `StreamSessionState`: the `DeviceSession` is the long-lived
/// connection to a specific paired wearable that the plugin owns on your
/// behalf. A `StreamSession` is one capability attached to that device
/// session (video streaming, in this plugin).
///
/// Surfaced by `MetaWearablesDat.deviceSessionStateStream()`. Mirrors the
/// `DeviceSessionState` enum in Meta's iOS / Android DAT SDKs.
enum DeviceSessionState {
  /// Created but not yet started.
  idle(0),

  /// `start()` has been called; the SDK is still negotiating with the
  /// device.
  starting(1),

  /// The device session is live; streams can be added.
  started(2),

  /// Temporarily paused (e.g. hinges closed, thermal limit).
  paused(3),

  /// `stop()` has been called; the device session is tearing down.
  stopping(4),

  /// Terminal state — a fresh `createSession()` is required to use the
  /// device again.
  stopped(5);

  const DeviceSessionState(this.value);

  /// The integer used on the platform channel.
  final int value;

  /// Maps a platform-channel integer to a [DeviceSessionState].
  static DeviceSessionState fromInt(int? value) {
    switch (value) {
      case 0:
        return DeviceSessionState.idle;
      case 1:
        return DeviceSessionState.starting;
      case 2:
        return DeviceSessionState.started;
      case 3:
        return DeviceSessionState.paused;
      case 4:
        return DeviceSessionState.stopping;
      case 5:
        return DeviceSessionState.stopped;
      case _:
        return DeviceSessionState.idle;
    }
  }
}
