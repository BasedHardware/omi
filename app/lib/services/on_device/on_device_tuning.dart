/// PLACEHOLDER numbers for on-device transcription. A benchmark is measuring the real values; every
/// figure the UI shows about model size or battery cost comes from this file, so replacing them is a
/// one-file change. Do not copy these into widgets.
abstract final class OnDeviceTuning {
  /// Download size of the speech model, in bytes. PLACEHOLDER until the benchmark lands.
  static const int modelSizeBytes = 600 * 1024 * 1024;

  /// Whisper model Android downloads for batch transcription. PLACEHOLDER until the benchmark picks one.
  static const String androidWhisperModel = 'base';

  /// Battery a day of "Every few hours" costs, in percent. PLACEHOLDER.
  static const int everyFewHoursBatteryPercentPerDay = 5;

  /// Battery an hour of conversation costs with "As you talk", in percent. PLACEHOLDER.
  static const int asYouTalkBatteryPercentPerHour = 8;

  /// How long "Every few hours" waits between runs on battery.
  static const Duration everyFewHoursInterval = Duration(hours: 3);

  /// Below this battery level, scheduled work on battery waits for a charger.
  static const int minBatteryPercentOnBattery = 30;

  /// Below this battery level even "Transcribe Now" waits for a charger.
  static const int criticalBatteryPercent = 10;
}
