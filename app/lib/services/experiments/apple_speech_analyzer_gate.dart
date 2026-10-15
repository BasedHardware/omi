import 'package:omi/utils/analytics/analytics_manager.dart';

/// Operational rollback: false/missing/offline keeps the improved engine on.
/// Lifecycle: ops_kill; owner: dazheng. No overflow or plan dependency.
abstract final class AppleSpeechAnalyzerGate {
  static const enabledFlag = 'mobile-speech-analyzer-disabled';

  static Future<bool> useNewEngine({Future<bool> Function(String)? readFlag}) async {
    try {
      final killed =
          await (readFlag ?? AnalyticsManager().isFeatureEnabled)(enabledFlag).timeout(const Duration(seconds: 2));
      return !killed;
    } catch (_) {
      return true;
    }
  }
}
