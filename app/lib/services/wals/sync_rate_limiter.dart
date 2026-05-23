import 'package:flutter/foundation.dart';
import 'package:omi/backend/preferences.dart';

/// Why uploads are currently paused.
/// - [rateLimit]   : server returned HTTP 429 (fair-use cap).
/// - [backendBusy] : server marked a job `failed` with the stale-guard error
///                   ("Job timed out (background worker likely died)") — i.e.
///                   the job sat queued because the backend pipeline is
///                   saturated and never picked it up. Not the user's fault;
///                   no `retryCount` bump and the UI surfaces this distinctly.
enum RateLimitReason { rateLimit, backendBusy }

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

  static const String _prefKeyUntil = 'syncRateLimitedUntilMs';
  static const String _prefKeyReason = 'syncRateLimitedReason';
  static const int _defaultCooldownSeconds = 1800; // 30 minutes
  static const int _maxCooldownSeconds = 24 * 60 * 60; // hard ceiling — guard against a misconfigured Retry-After

  bool get isLimited {
    final until = SharedPreferencesUtil().getInt(_prefKeyUntil);
    return until > 0 && DateTime.now().millisecondsSinceEpoch < until;
  }

  DateTime? get until {
    final ms = SharedPreferencesUtil().getInt(_prefKeyUntil);
    return ms > 0 ? DateTime.fromMillisecondsSinceEpoch(ms) : null;
  }

  RateLimitReason? get reason {
    if (!isLimited) return null;
    final name = SharedPreferencesUtil().getString(_prefKeyReason);
    return RateLimitReason.values.asNameMap()[name] ?? RateLimitReason.rateLimit;
  }

  /// Pause uploads. Honors the server's Retry-After (seconds) when present,
  /// otherwise falls back to a 30-minute cooldown. [reason] picks the
  /// user-facing message ("Fair-use limit reached" vs "Backend busy").
  void markLimited({int? retryAfterSeconds, RateLimitReason reason = RateLimitReason.rateLimit}) {
    final requested =
        (retryAfterSeconds != null && retryAfterSeconds > 0) ? retryAfterSeconds : _defaultCooldownSeconds;
    final secs = requested > _maxCooldownSeconds ? _maxCooldownSeconds : requested;
    final untilMs = DateTime.now().add(Duration(seconds: secs)).millisecondsSinceEpoch;
    SharedPreferencesUtil().saveInt(_prefKeyUntil, untilMs);
    SharedPreferencesUtil().saveString(_prefKeyReason, reason.name);
    notifyListeners();
  }

  /// Clear the cooldown after any successful upload.
  void clear() {
    SharedPreferencesUtil().saveInt(_prefKeyUntil, 0);
    SharedPreferencesUtil().saveString(_prefKeyReason, '');
    notifyListeners();
  }
}
