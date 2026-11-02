import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';

/// When recordings waiting on the phone get transcribed.
enum OnDeviceSchedule {
  /// Only on a charger: almost no battery. The default.
  whileCharging('while_charging'),

  /// In short bursts every few hours on battery.
  everyFewHours('every_few_hours'),

  /// Continuously, as the conversation happens. Costs the most battery.
  asYouTalk('as_you_talk');

  const OnDeviceSchedule(this.storageId);

  /// Persisted value; stable across renames of the Dart identifier.
  final String storageId;

  static OnDeviceSchedule fromStorage(String? raw) {
    for (final schedule in values) {
      if (schedule.storageId == raw) return schedule;
    }
    return OnDeviceSchedule.whileCharging;
  }
}

/// The reader's on-device transcription choices.
@immutable
class OnDeviceSettings {
  const OnDeviceSettings({
    this.enabled = false,
    this.saveLiveHours = false,
    this.schedule = OnDeviceSchedule.whileCharging,
    this.wifiOnlyDownload = true,
    this.keepEverythingOnDevice = false,
  });

  /// Transcribe on this phone once live hours run out.
  final bool enabled;

  /// Transcribe on this phone even while live hours remain, to save them (paid plans).
  final bool saveLiveHours;

  final OnDeviceSchedule schedule;

  /// Download the speech model only on Wi-Fi.
  final bool wifiOnlyDownload;

  /// Transcripts only: nothing, not even transcript text, is sent to Omi Cloud for a summary.
  final bool keepEverythingOnDevice;

  OnDeviceSettings copyWith({
    bool? enabled,
    bool? saveLiveHours,
    OnDeviceSchedule? schedule,
    bool? wifiOnlyDownload,
    bool? keepEverythingOnDevice,
  }) {
    return OnDeviceSettings(
      enabled: enabled ?? this.enabled,
      saveLiveHours: saveLiveHours ?? this.saveLiveHours,
      schedule: schedule ?? this.schedule,
      wifiOnlyDownload: wifiOnlyDownload ?? this.wifiOnlyDownload,
      keepEverythingOnDevice: keepEverythingOnDevice ?? this.keepEverythingOnDevice,
    );
  }

  @override
  bool operator ==(Object other) =>
      other is OnDeviceSettings &&
      other.enabled == enabled &&
      other.saveLiveHours == saveLiveHours &&
      other.schedule == schedule &&
      other.wifiOnlyDownload == wifiOnlyDownload &&
      other.keepEverythingOnDevice == keepEverythingOnDevice;

  @override
  int get hashCode => Object.hash(enabled, saveLiveHours, schedule, wifiOnlyDownload, keepEverythingOnDevice);
}

/// Reads and writes [OnDeviceSettings] through [SharedPreferencesUtil].
class OnDeviceSettingsStore {
  OnDeviceSettingsStore({SharedPreferencesUtil? prefs}) : _prefs = prefs ?? SharedPreferencesUtil();

  final SharedPreferencesUtil _prefs;

  static const enabledKey = 'onDeviceTranscription.enabled';
  static const saveLiveHoursKey = 'onDeviceTranscription.saveLiveHours';
  static const scheduleKey = 'onDeviceTranscription.schedule';
  static const wifiOnlyKey = 'onDeviceTranscription.wifiOnlyDownload';
  static const keepOnDeviceKey = 'onDeviceTranscription.keepEverythingOnDevice';

  static const _defaults = OnDeviceSettings();

  OnDeviceSettings load() {
    return OnDeviceSettings(
      enabled: _prefs.getBool(enabledKey, defaultValue: _defaults.enabled),
      saveLiveHours: _prefs.getBool(saveLiveHoursKey, defaultValue: _defaults.saveLiveHours),
      schedule: OnDeviceSchedule.fromStorage(_prefs.getString(scheduleKey)),
      wifiOnlyDownload: _prefs.getBool(wifiOnlyKey, defaultValue: _defaults.wifiOnlyDownload),
      keepEverythingOnDevice: _prefs.getBool(keepOnDeviceKey, defaultValue: _defaults.keepEverythingOnDevice),
    );
  }

  Future<void> save(OnDeviceSettings settings) async {
    await Future.wait([
      _prefs.saveBool(enabledKey, settings.enabled),
      _prefs.saveBool(saveLiveHoursKey, settings.saveLiveHours),
      _prefs.saveString(scheduleKey, settings.schedule.storageId),
      _prefs.saveBool(wifiOnlyKey, settings.wifiOnlyDownload),
      _prefs.saveBool(keepOnDeviceKey, settings.keepEverythingOnDevice),
    ]);
  }
}
