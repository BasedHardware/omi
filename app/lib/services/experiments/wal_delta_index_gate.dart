import 'package:omi/utils/analytics/analytics_manager.dart';

/// Operational kill switch for the delta WAL index writer.
/// False/missing/offline/error keeps the delta writer on (ops_kill, owner dazheng);
/// true makes the next app launch save every index change through the
/// full-snapshot writer that shipped before the delta worker. Both write the
/// same on-disk format, so flipping it either way needs no migration.
abstract final class WalDeltaIndexGate {
  static const killSwitchFlag = 'mobile-wal-delta-index-off';

  static Future<bool> deltaWriterAllowed({Future<bool> Function(String)? readFlag}) async {
    try {
      final killed =
          await (readFlag ?? AnalyticsManager().isFeatureEnabled)(killSwitchFlag).timeout(const Duration(seconds: 1));
      return !killed;
    } catch (_) {
      return true;
    }
  }
}
