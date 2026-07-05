/// State of an active [StreamSession] (the video-streaming capability
/// attached to a `DeviceSession`).
///
/// Surfaced by `MetaWearablesDat.streamSessionStateStream()`. Mirrors the
/// underlying `StreamSessionState` from Meta's DAT SDKs.
enum StreamSessionState {
  /// No stream is active.
  stopped(0),

  /// The stream has been requested but the SDK is still waiting for the
  /// device to be ready (e.g. paired but not yet connected).
  waitingForDevice(1),

  /// The stream has been opened and is configuring.
  starting(2),

  /// Frames are flowing.
  streaming(3),

  /// The stream is paused. Pauses can be initiated by the SDK (thermal,
  /// hinges closed, app backgrounded) and may not be triggerable from the
  /// host app on every device generation.
  paused(4),

  /// The stream is being torn down.
  stopping(5);

  const StreamSessionState(this.value);

  /// The integer used on the platform channel.
  final int value;

  /// Maps a platform-channel integer to a [StreamSessionState].
  static StreamSessionState fromInt(int? value) {
    switch (value) {
      case 0:
        return StreamSessionState.stopped;
      case 1:
        return StreamSessionState.waitingForDevice;
      case 2:
        return StreamSessionState.starting;
      case 3:
        return StreamSessionState.streaming;
      case 4:
        return StreamSessionState.paused;
      case 5:
        return StreamSessionState.stopping;
      case _:
        return StreamSessionState.stopped;
    }
  }
}
