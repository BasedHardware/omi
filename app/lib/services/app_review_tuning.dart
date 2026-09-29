import 'dart:convert';

import 'package:omi/services/app_review_policy.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

/// An optional PostHog flag payload: {"reading_seconds": 5, "cooldown_days": 30}.
/// Invalid or unavailable values retain the shipped defaults.
abstract final class AppReviewTuning {
  static const flag = 'mobile_store_review_tuning';
  static const defaultReadingSeconds = 5;

  static int parseInt(Object? payload, String key, int fallback, int maximum) {
    if (payload is String) {
      try {
        payload = jsonDecode(payload);
      } catch (_) {
        return fallback;
      }
    }
    if (payload is! Map || payload[key] is! int) return fallback;
    final value = payload[key] as int;
    return value >= 1 && value <= maximum ? value : fallback;
  }

  static Future<Object?> _payload() async {
    return AnalyticsManager().getFeatureFlagPayload(flag);
  }

  static Future<Duration> readingDuration() async =>
      Duration(seconds: parseInt(await _payload(), 'reading_seconds', defaultReadingSeconds, 30));

  static Future<Duration> cooldown() async =>
      Duration(days: parseInt(await _payload(), 'cooldown_days', AppReviewPolicy.requestCooldown.inDays, 365));
}
