import 'package:omi/utils/analytics/analytics_manager.dart';

/// Operational kill switch for hiding unbelievable Omi battery readings
/// (BatteryDisplayPolicy). False/missing/offline/error keeps the guard on;
/// true shows every reading exactly as the pendant reports it, from the next
/// connection after the flag is read. Raw readings are never changed either way.
abstract final class BatteryDisplayGuardGate {
  static const killSwitchFlag = 'mobile-battery-display-guard-off';

  static Future<bool> allowed({Future<bool> Function(String)? readFlag}) async {
    try {
      final killed =
          await (readFlag ?? AnalyticsManager().isFeatureEnabled)(killSwitchFlag).timeout(const Duration(seconds: 1));
      return !killed;
    } catch (_) {
      return true;
    }
  }
}
