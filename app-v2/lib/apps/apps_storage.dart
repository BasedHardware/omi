import 'package:hive/hive.dart';

/// Hive box names for the Apps tab.
///
/// One box for now:
///   * [prefs] — per-app user preferences (currently just the two-way-sync
///     opt-in map). Catalog + enabled-set are NOT persisted — they refetch
///     from `/v2/apps` and `/v1/apps/enabled` on every cold start, so caching
///     them risks showing stale install state right after the user toggles
///     a plugin on another device.
class AppsBoxes {
  AppsBoxes._();

  /// Persisted per-app prefs. Today this holds the `twoWaySync` opt-in map
  /// keyed by appId; see `AppsProvider._persistTwoWaySync`.
  static const String prefs = 'apps.prefs.v1';

  /// Wipes per-app prefs. Called by the debug "Reset onboarding" flow so
  /// dev resets are total.
  static Future<void> clearAll() => Hive.box<Map>(prefs).clear();
}
