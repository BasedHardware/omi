import 'package:hive/hive.dart';

/// Hive box names for the Plan tab.
///
/// Single box for now:
///   * [prefs] — per-user UI prefs (currently just the pivot mode: by date /
///     project / status). Keeps the picker's choice across cold starts so
///     the user doesn't have to re-pick on every launch.
class PlanBoxes {
  PlanBoxes._();

  /// Persisted Plan-screen prefs. Today this holds the pivot-picker choice
  /// keyed under [pivotKey]; see `PlanPivotPicker`.
  static const String prefs = 'plan.prefs.v1';

  /// Hive key inside [prefs] for the saved pivot mode (string name of the
  /// `PlanPivot` enum).
  static const String pivotKey = 'pivot';

  /// Wipes Plan prefs. Called by debug "Reset onboarding" flow so dev
  /// resets are total.
  static Future<void> clearAll() => Hive.box<dynamic>(prefs).clear();
}
