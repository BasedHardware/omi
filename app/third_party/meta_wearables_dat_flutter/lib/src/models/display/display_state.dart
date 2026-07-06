/// Lifecycle state of the [Display] capability attached to a `DeviceSession`.
///
/// Surfaced by `MetaWearablesDat.displayStateStream()`. Mirrors the
/// `DisplayState` enum in Meta's iOS / Android DAT SDKs (added in DAT 0.7.0).
enum DisplayState {
  /// The display capability has been requested and is being set up.
  starting(0),

  /// The display is ready; views can be sent with `sendDisplayView`.
  started(1),

  /// The display is being torn down.
  stopping(2),

  /// The display is no longer attached.
  stopped(3);

  const DisplayState(this.value);

  /// The integer used on the platform channel.
  final int value;

  /// Maps a platform-channel integer to a [DisplayState].
  static DisplayState fromInt(int? value) {
    switch (value) {
      case 0:
        return DisplayState.starting;
      case 1:
        return DisplayState.started;
      case 2:
        return DisplayState.stopping;
      case 3:
        return DisplayState.stopped;
      case _:
        return DisplayState.stopped;
    }
  }
}
