import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/startup/boot_journal.dart';
import 'package:omi/startup_failure_app.dart';

/// Persisted failure streak. A recovery boot does not clear it; only a full boot does.
class BootRecovery {
  BootRecovery(this.prefs, {DateTime Function()? now}) : _now = now ?? DateTime.now;

  static const schemaVersion = 1;
  static const _countKey = 'boot.failure_count';
  static const _stageKey = 'boot.failure_stage';
  static const _timeKey = 'boot.failure_at_ms';
  static const schemaKey = 'boot.schema_version';
  static const window = Duration(minutes: 10);
  static const skippedStages = {'restore_onboarding', 'bind_owner', 'opus_load', 'ble_setup', 'service_manager_start'};

  static bool safeModeActive = false;
  final SharedPreferences prefs;
  final DateTime Function() _now;

  int get count => prefs.get(_countKey) is int ? prefs.getInt(_countKey)! : 0;
  String get failingStage => prefs.get(_stageKey) is String ? prefs.getString(_stageKey)! : '';
  int get previousSchema => prefs.get(schemaKey) is int ? prefs.getInt(schemaKey)! : 0;
  bool get needsMigration => previousSchema < schemaVersion;
  bool get shouldRecover {
    final lastFailure = prefs.get(_timeKey);
    final age = lastFailure is int ? _now().millisecondsSinceEpoch - lastFailure : -1;
    return count >= 3 && age >= 0 && age <= window.inMilliseconds;
  }

  static bool skipStage(String stage) => safeModeActive && skippedStages.contains(stage);
  static bool countsFailure(Object error) => error is! StartupConfigurationError;

  Future<int> failed(String stage) async {
    final now = _now().millisecondsSinceEpoch;
    final prior = prefs.get(_timeKey);
    final sameWindow = prior is int && now >= prior && now - prior <= window.inMilliseconds;
    final next = sameWindow && failingStage == stage ? count + 1 : 1;
    await prefs.setInt(_countKey, next);
    await prefs.setString(_stageKey, stage);
    await prefs.setInt(_timeKey, now);
    return next;
  }

  Future<void> fullBootSucceeded() async {
    await prefs.setInt(schemaKey, schemaVersion);
    await prefs.setInt(_countKey, 0);
    await prefs.remove(_stageKey);
    await prefs.remove(_timeKey);
    safeModeActive = false;
  }

  /// A process killed inside a stage has no Dart catch. Count its last begin on next launch.
  Future<void> countInterruptedBoot(BootJournal journal) async {
    final entries = await journal.read();
    if (entries.isNotEmpty && entries.last['state'] == 'begin' && entries.last['stage'] is String) {
      final stage = entries.last['stage'] as String;
      await failed(stage);
      await journal.record(stage, 'interrupted');
    }
  }
}
