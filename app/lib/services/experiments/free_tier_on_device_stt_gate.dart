import 'package:omi/utils/analytics/analytics_manager.dart';

/// Operational kill switch for live on-device transcription past the cloud cap (S17).
/// False/missing/offline/error keeps it on (ops_kill, owner free-tier-on-device); true returns
/// new sockets to today's Omi socket, where the server holds the audio at the cap.
abstract final class FreeTierOnDeviceSttGate {
  static const killSwitchFlag = 'mobile-free-tier-on-device-stt-disabled';

  static Future<bool> killed({Future<bool> Function(String key)? readFlag}) async {
    try {
      return await (readFlag ?? AnalyticsManager().isFeatureEnabled)(killSwitchFlag)
          .timeout(const Duration(seconds: 1));
    } catch (_) {
      return false;
    }
  }
}
