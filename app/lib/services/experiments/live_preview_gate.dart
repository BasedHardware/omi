import 'package:omi/utils/analytics/analytics_manager.dart';

/// Operational kill switch for the mobile local-preview request.
/// False/missing/offline/error keeps the request on (ops_kill, owner dazheng);
/// true makes the client stop declaring `local_preview=enabled`, which returns
/// the session to today's cloud live transcript on the next socket.
abstract final class LivePreviewGate {
  static const killSwitchFlag = 'mobile-local-preview-disabled';

  static Future<bool> requestAllowed({Future<bool> Function(String)? readFlag}) async {
    try {
      final killed =
          await (readFlag ?? AnalyticsManager().isFeatureEnabled)(killSwitchFlag).timeout(const Duration(seconds: 1));
      return !killed;
    } catch (_) {
      return true;
    }
  }
}
