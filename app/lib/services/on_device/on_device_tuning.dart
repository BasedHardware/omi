/// Sizes from the internal pendant sample benchmark (2026-10-14).
/// Phone energy is unmeasured; battery thresholds below are conservative policy estimates.
abstract final class OnDeviceTuning {
  static const parakeetSizeBytes = 443 * 1024 * 1024;
  static const decodeChunkSeconds = 30;

  /// Download size of the speech model, in bytes. whisper.cpp tiny; Parakeet v2 is 443 MiB. Apple assets are OS-managed.
  static const int modelSizeBytes = 74 * 1024 * 1024;

  /// Whisper model Android downloads for batch transcription. Bounded 30-second decoding.
  static const String androidWhisperModel = 'tiny';

  /// How long "Every few hours" waits between runs on battery.
  static const Duration everyFewHoursInterval = Duration(hours: 3);

  /// Below this battery level, scheduled work on battery waits for a charger.
  static const int minBatteryPercentOnBattery = 30;

  /// Below this battery level even "Transcribe Now" waits for a charger.
  static const int criticalBatteryPercent = 10;
}
