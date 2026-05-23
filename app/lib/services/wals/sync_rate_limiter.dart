import 'package:flutter/foundation.dart';
import 'package:omi/backend/preferences.dart';

/// Account-global cooldown for fair-use throttling (HTTP 429) on sync uploads.
///
/// When the server rate-limits uploads, the app must stop firing requests
/// until the window passes — otherwise it hammers the endpoint every minute,
/// amplifies the 429 storm, and burns each recording's retry budget so a
/// throttle is mislabelled as "couldn't process". Persisted so a relaunch
/// during the window doesn't immediately resume hammering.
class SyncRateLimiter extends ChangeNotifier {
  SyncRateLimiter._();
  static final SyncRateLimiter instance = SyncRateLimiter._();

  static const String _prefKey = 'syncRateLimitedUntilMs';
  static const int _defaultCooldownSeconds = 1800; // 30 minutes

  bool get isLimited {
    final until = SharedPreferencesUtil().getInt(_prefKey);
    return until > 0 && DateTime.now().millisecondsSinceEpoch < until;
  }

  DateTime? get until {
    final ms = SharedPreferencesUtil().getInt(_prefKey);
    return ms > 0 ? DateTime.fromMillisecondsSinceEpoch(ms) : null;
  }

  /// Pause uploads. Honors the server's Retry-After (seconds) when present,
  /// otherwise falls back to a 30-minute cooldown.
  void markLimited({int? retryAfterSeconds}) {
    final secs = (retryAfterSeconds != null && retryAfterSeconds > 0) ? retryAfterSeconds : _defaultCooldownSeconds;
    final untilMs = DateTime.now().add(Duration(seconds: secs)).millisecondsSinceEpoch;
    SharedPreferencesUtil().saveInt(_prefKey, untilMs);
    notifyListeners();
  }

  /// Clear the cooldown after any successful upload.
  void clear() {
    SharedPreferencesUtil().saveInt(_prefKey, 0);
    notifyListeners();
  }
}
