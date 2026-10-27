import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/preferences.dart';

/// Why uploads are currently paused.
/// - [fairUse]     : server explicitly returned a fair-use 429. Persisted —
///                   mirrors server-side enforcement that survives client
///                   restarts (the server keeps a 30-day restrict window).
/// - [backendBusy] : server marked a job `failed` with the stale-guard error
///                   ("Job timed out (background worker likely died)") — i.e.
///                   the job sat queued because the backend pipeline is
///                   saturated and never picked it up. In-memory only — once
///                   the app restarts, the cooldown clears so the user sees
///                   fresh state if the server has since recovered.
/// - [dispatchHold]: a per-account maintenance fence asked this account to
///                   wait. Not a capacity problem: uploads resume on their own
///                   when the fence lifts, so its copy must not say the
///                   servers are busy.
enum RateLimitReason { fairUse, backendBusy, dispatchHold, edgeThrottle }

/// Account-global cooldown for rate limiting (HTTP 429) on sync uploads.
///
/// When the server rate-limits uploads, the app must stop firing requests
/// until the window passes — otherwise it hammers the endpoint every minute,
/// amplifies the 429 storm, and burns each recording's retry budget so a
/// throttle is mislabelled as "couldn't process".
///
/// `fairUse` cooldowns are persisted (a relaunch during the window
/// shouldn't immediately resume hammering). `backendBusy` cooldowns are
/// in-memory only — they reflect transient server pressure and should not
/// survive an app restart that the user just did to "try again".
class SyncRateLimiter extends ChangeNotifier {
  SyncRateLimiter._() {
    // Migration: older versions persisted backendBusy cooldowns and used
    // `rateLimit` for every unclassified 429. Neither is evidence of explicit
    // fair-use enforcement, so neither may survive as a fair-use banner.
    final persistedReason = SharedPreferencesUtil().getString(_prefKeyReason);
    if (persistedReason == RateLimitReason.backendBusy.name || persistedReason == 'rateLimit') {
      SharedPreferencesUtil().saveInt(_prefKeyUntil, 0);
      SharedPreferencesUtil().saveString(_prefKeyReason, '');
    }
    // Migration: the retired backfill lane persisted its own cooldown, and a
    // live value there gates uploads with no way left to clear it.
    SharedPreferencesUtil().saveInt(_prefKeyRetiredBackfillUntil, 0);
    _scheduleExpiryNotification();
  }
  DateTime Function() _clock = DateTime.now;

  @visibleForTesting
  set clockForTesting(DateTime Function()? clock) {
    _clock = clock ?? DateTime.now;
    _scheduleExpiryNotification();
  }

  static final SyncRateLimiter instance = SyncRateLimiter._();

  static const String _prefKeyUntil = 'syncRateLimitedUntilMs';
  static const String _prefKeyReason = 'syncRateLimitedReason';
  static const String _prefKeyRetiredBackfillUntil = 'syncBackfillLimitedUntilMs';
  static const int _defaultCooldownSeconds = 1800; // 30 minutes
  static const int _maxFairUseCooldownSeconds = 30 * 24 * 60 * 60;
  static const int _maxBackendBusyCooldownSeconds = 24 * 60 * 60;
  static const int _defaultDispatchHoldCooldownSeconds = 60;
  static const int _maxDispatchHoldCooldownSeconds = 60 * 60;

  // In-memory cooldown for backendBusy. Intentionally not persisted so an
  // app restart re-probes the backend state instead of trusting a stale
  // local timer.
  int _backendBusyUntilMs = 0;
  RateLimitReason _inMemoryReason = RateLimitReason.backendBusy;
  int _dispatchHoldBackoffLevel = 0;
  int _dispatchHoldUntilMs = 0;
  int _dispatchHoldLastCooldownMs = 0;
  Timer? _expiryTimer;

  /// Whether a server-confirmed fair-use cooldown is persisted, including an
  /// expired one that still needs authoritative reconciliation before retry.
  bool get hasPersistedFairUseState =>
      SharedPreferencesUtil().getString(_prefKeyReason) == RateLimitReason.fairUse.name &&
      SharedPreferencesUtil().getInt(_prefKeyUntil) > 0;

  bool get isFairUseLimited {
    if (!hasPersistedFairUseState) return false;
    final until = SharedPreferencesUtil().getInt(_prefKeyUntil);
    return until > _clock().millisecondsSinceEpoch;
  }

  bool get isBackendBusyLimited =>
      _inMemoryReason == RateLimitReason.backendBusy && _backendBusyUntilMs > _clock().millisecondsSinceEpoch;

  @visibleForTesting
  int get dispatchHoldBackoffLevelForTesting => _dispatchHoldBackoffLevel;

  bool get isLimited {
    final now = _clock().millisecondsSinceEpoch;
    if (_backendBusyUntilMs > now) return true;
    return isFairUseLimited;
  }

  DateTime? get until {
    final now = _clock().millisecondsSinceEpoch;
    final persisted = hasPersistedFairUseState ? SharedPreferencesUtil().getInt(_prefKeyUntil) : 0;
    final inMemory = _backendBusyUntilMs;
    final candidates = <int>[if (inMemory > now) inMemory, if (persisted > now) persisted];
    if (candidates.isEmpty) return null;
    return DateTime.fromMillisecondsSinceEpoch(candidates.reduce((a, b) => a > b ? a : b));
  }

  RateLimitReason? get reason {
    final now = _clock().millisecondsSinceEpoch;
    final persisted = hasPersistedFairUseState ? SharedPreferencesUtil().getInt(_prefKeyUntil) : 0;
    final busyActive = _backendBusyUntilMs > now;
    final rateActive = persisted > now;
    if (!busyActive && !rateActive) return null;
    // Match `until`'s max-based pick so reason and deadline refer to the same cooldown.
    if (busyActive && (!rateActive || _backendBusyUntilMs >= persisted)) {
      return _inMemoryReason;
    }
    return RateLimitReason.fairUse;
  }

  /// Pause uploads. Honors the server's Retry-After (seconds) when present,
  /// otherwise falls back to a 30-minute cooldown. [reason] picks the
  /// user-facing message ("Fair-use limit reached" vs "Backend busy") and
  /// also picks the persistence mode (fairUse persists, backendBusy is
  /// in-memory only).
  void markLimited({int? retryAfterSeconds, RateLimitReason reason = RateLimitReason.fairUse}) {
    final requested =
        (retryAfterSeconds != null && retryAfterSeconds > 0) ? retryAfterSeconds : _defaultCooldownSeconds;
    final maxCooldown = reason == RateLimitReason.fairUse ? _maxFairUseCooldownSeconds : _maxBackendBusyCooldownSeconds;
    final secs = requested > maxCooldown ? maxCooldown : requested;
    final untilMs = _clock().add(Duration(seconds: secs)).millisecondsSinceEpoch;
    if (reason != RateLimitReason.fairUse) {
      if (untilMs >= _backendBusyUntilMs) {
        _inMemoryReason = reason;
        _backendBusyUntilMs = untilMs;
      }
    } else {
      SharedPreferencesUtil().saveInt(_prefKeyUntil, untilMs);
      SharedPreferencesUtil().saveString(_prefKeyReason, reason.name);
    }
    _scheduleExpiryNotification();
    notifyListeners();
  }

  /// Pause after a scoped destructive-operation fence. Each further hold
  /// doubles the server's Retry-After, up to one hour. The next upload can only
  /// run after a cooldown expires, so a hold that arrives soon after expiry is
  /// the same fence still held and keeps the backoff. A successful upload
  /// resets it, and so does a quiet gap of twice the last cooldown.
  void markDispatchHoldLimited({int? retryAfterSeconds}) {
    final nowMs = _clock().millisecondsSinceEpoch;
    if (_dispatchHoldUntilMs > 0 && nowMs - _dispatchHoldUntilMs > 2 * _dispatchHoldLastCooldownMs) {
      _dispatchHoldBackoffLevel = 0;
    }

    var seconds =
        (retryAfterSeconds != null && retryAfterSeconds > 0) ? retryAfterSeconds : _defaultDispatchHoldCooldownSeconds;
    for (var i = 0; i < _dispatchHoldBackoffLevel && seconds < _maxDispatchHoldCooldownSeconds; i++) {
      seconds = seconds > _maxDispatchHoldCooldownSeconds ~/ 2 ? _maxDispatchHoldCooldownSeconds : seconds * 2;
    }
    if (seconds > _maxDispatchHoldCooldownSeconds) seconds = _maxDispatchHoldCooldownSeconds;
    if (_dispatchHoldBackoffLevel < 16) _dispatchHoldBackoffLevel++;

    _dispatchHoldLastCooldownMs = Duration(seconds: seconds).inMilliseconds;
    _dispatchHoldUntilMs = nowMs + _dispatchHoldLastCooldownMs;
    final untilMs = _dispatchHoldUntilMs;
    if (untilMs >= _backendBusyUntilMs) {
      // The fence's own reason, so cooldown copy never blames server capacity
      // for what is a per-account hold that lifts on its own.
      _inMemoryReason = RateLimitReason.dispatchHold;
      _backendBusyUntilMs = untilMs;
    }
    _scheduleExpiryNotification();
    notifyListeners();
  }

  int? get activeRetryAfterSeconds {
    final deadline = until;
    if (deadline == null) return null;
    final remainingMs = deadline.millisecondsSinceEpoch - _clock().millisecondsSinceEpoch;
    if (remainingMs <= 0) return null;
    return (remainingMs / 1000).ceil();
  }

  /// Clear the cooldown after any successful upload.
  void clear() {
    _backendBusyUntilMs = 0;
    _dispatchHoldBackoffLevel = 0;
    _dispatchHoldUntilMs = 0;
    _dispatchHoldLastCooldownMs = 0;
    SharedPreferencesUtil().saveInt(_prefKeyUntil, 0);
    SharedPreferencesUtil().saveString(_prefKeyReason, '');
    _scheduleExpiryNotification();
    notifyListeners();
  }

  /// Clear only the persisted fair-use rate-limit cooldown (HTTP 429),
  /// preserving any active in-memory backend-busy cooldown. Used when a
  /// fair-use status refresh confirms the restriction was lifted but the
  /// backend may still be saturated and should keep its own backoff.
  void clearRateLimit() {
    SharedPreferencesUtil().saveInt(_prefKeyUntil, 0);
    SharedPreferencesUtil().saveString(_prefKeyReason, '');
    _scheduleExpiryNotification();
    notifyListeners();
  }

  void _scheduleExpiryNotification() {
    _expiryTimer?.cancel();
    final now = _clock().millisecondsSinceEpoch;
    final deadlines = <int>[
      if (_backendBusyUntilMs > now) _backendBusyUntilMs,
      if (hasPersistedFairUseState && SharedPreferencesUtil().getInt(_prefKeyUntil) > now)
        SharedPreferencesUtil().getInt(_prefKeyUntil),
    ];
    if (deadlines.isEmpty) return;
    final next = deadlines.reduce((a, b) => a < b ? a : b);
    _expiryTimer = Timer(Duration(milliseconds: next - now + 1), () {
      notifyListeners();
      _scheduleExpiryNotification();
    });
  }
}
