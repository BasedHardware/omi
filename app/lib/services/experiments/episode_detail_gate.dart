import 'package:omi/utils/analytics/analytics_manager.dart';

/// Default-on episode detail, using the same identity-fenced reader as Home flags.
abstract final class EpisodeDetailGate {
  static const killSwitchFlag = 'mobile-episode-detail-redesign-disabled';

  static Future<bool> enabled({Future<bool> Function(String)? readFlag}) async {
    try {
      return !await (readFlag ?? AnalyticsManager().isFeatureEnabled)(killSwitchFlag)
          .timeout(const Duration(seconds: 1));
    } catch (_) {
      return true;
    }
  }
}
