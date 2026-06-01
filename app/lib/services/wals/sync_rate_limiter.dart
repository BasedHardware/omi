import 'package:flutter/foundation.dart';
import 'package:omi/backend/preferences.dart';

/// Why uploads are currently paused.
/// - [rateLimit]   : server returned HTTP 429 (fair-use cap). Persisted —
///                   mirrors server-side enforcement that survives client
///                   restarts (the server keeps a 30-day restrict window).
/// - [backendBusy] : server marked a job `failed` with the stale-guard error
///                   ("Job timed out (background worker likely died)") — i.e.
///                   the job sat queued because the backend pipeline is
///                   saturated and never picked it up. In-memory only — once
///                   the app restarts, the cooldown clears so the user sees
///                   fresh state if the server has since recovered.
enum RateLimitReason { rateLimit, backendBusy }

/// Account-global cooldown for fair-use throttling (HTTP 429) on sync uploads.
///
/// When the server rate-limits uploads, the app must stop firing requests
/// until the window passes — otherwise it hammers the endpoint every minute,
/// amplifies the 429 storm, and burns each recording's retry budget so a
/// throttle is mislabelled as "couldn't process".
///
/// `rateLimit` cooldowns are persisted (a relaunch during the window
/// shouldn't immediately resume hammering). `backendBusy` cooldowns are
/// in-memory only — they reflect transient server pressure and should not
/// survive an app restart that the user just did to "try again".
class SyncRateLimiter extends ChangeNotifier {
  SyncRateLimiter._() {
    // Migration: older versions persisted backendBusy cooldowns. Clear any
    // stuck persisted backendBusy state so users coming from a healthy
    // server don't keep seeing "Omi servers are busy" indefinitely.
    final persistedReason = SharedPreferencesUtil().getString(_prefKeyReason);
    if (persistedReason == RateLimitReason.backendBusy.name) {
      SharedPreferencesUtil().saveInt(_prefKeyUntil, 0);
      SharedPreferencesUtil().saveString(_prefKeyReason, '');
    }
  }
  static final SyncRateLimiter instance = SyncRateLimiter._();

  static const String _prefKeyUntil = 'syncRateLimitedUntilMs';
  static const String _prefKeyReason = 'syncRateLimitedReason';
  static const int _defaultCooldownSeconds = 1800; // 30 minutes
  static const int _maxCooldownSeconds = 24 * 60 * 60; // hard ceiling — guard against a misconfigured Retry-After

  // In-memory cooldown for backendBusy. Intentionally not persisted so an
  // app restart re-probes the backend state instead of trusting a stale
  // local timer.
  int _backendBusyUntilMs = 0;

  bool get isLimited {
    final now = DateTime.now().millisecondsSinceEpoch;
    if (_backendBusyUntilMs > now) return true;
    final until = SharedPreferencesUtil().getInt(_prefKeyUntil);
    return until > 0 && now < until;
  }

  DateTime? get until {
    final now = DateTime.now().millisecondsSinceEpoch;
    final persisted = SharedPreferencesUtil().getInt(_prefKeyUntil);
    final inMemory = _backendBusyUntilMs;
    final candidates = <int>[if (inMemory > now) inMemory, if (persisted > now) persisted];
    if (candidates.isEmpty) return null;
    return DateTime.fromMillisecondsSinceEpoch(candidates.reduce((a, b) => a > b ? a : b));
  }

  RateLimitReason? get reason {
    final now = DateTime.now().millisecondsSinceEpoch;
    final persisted = SharedPreferencesUtil().getInt(_prefKeyUntil);
    final busyActive = _backendBusyUntilMs > now;
    final rateActive = persisted > now;
    if (!busyActive && !rateActive) return null;
    // Match `until`'s max-based pick so reason and deadline refer to the same cooldown.
    if (busyActive && (!rateActive || _backendBusyUntilMs >= persisted)) {
      return RateLimitReason.backendBusy;
    }
    final name = SharedPreferencesUtil().getString(_prefKeyReason);
    return RateLimitReason.values.asNameMap()[name] ?? RateLimitReason.rateLimit;
  }

  /// Pause uploads. Honors the server's Retry-After (seconds) when present,
  /// otherwise falls back to a 30-minute cooldown. [reason] picks the
  /// user-facing message ("Fair-use limit reached" vs "Backend busy") and
  /// also picks the persistence mode (rateLimit persists, backendBusy is
  /// in-memory only).
  void markLimited({int? retryAfterSeconds, RateLimitReason reason = RateLimitReason.rateLimit}) {
    final requested =
        (retryAfterSeconds != null && retryAfterSeconds > 0) ? retryAfterSeconds : _defaultCooldownSeconds;
    final secs = requested > _maxCooldownSeconds ? _maxCooldownSeconds : requested;
    final untilMs = DateTime.now().add(Duration(seconds: secs)).millisecondsSinceEpoch;
    if (reason == RateLimitReason.backendBusy) {
      _backendBusyUntilMs = untilMs;
    } else {
      SharedPreferencesUtil().saveInt(_prefKeyUntil, untilMs);
      SharedPreferencesUtil().saveString(_prefKeyReason, reason.name);
    }
    notifyListeners();
  }

  /// Clear the cooldown after any successful upload.
  void clear() {
    _backendBusyUntilMs = 0;
    SharedPreferencesUtil().saveInt(_prefKeyUntil, 0);
    SharedPreferencesUtil().saveString(_prefKeyReason, '');
    notifyListeners();
  }
}
