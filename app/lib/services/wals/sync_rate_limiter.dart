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
enum RateLimitReason { fairUse, backfillPaced, backendBusy }

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
    _scheduleExpiryNotification();
  }
  static final SyncRateLimiter instance = SyncRateLimiter._();

  static const String _prefKeyUntil = 'syncRateLimitedUntilMs';
  static const String _prefKeyReason = 'syncRateLimitedReason';
  static const String _prefKeyBackfillUntil = 'syncBackfillLimitedUntilMs';
  static const int _defaultCooldownSeconds = 1800; // 30 minutes
  static const int _maxFairUseCooldownSeconds = 30 * 24 * 60 * 60;
  static const int _maxBackendBusyCooldownSeconds = 24 * 60 * 60;

  // In-memory cooldown for backendBusy. Intentionally not persisted so an
  // app restart re-probes the backend state instead of trusting a stale
  // local timer.
  int _backendBusyUntilMs = 0;
  Timer? _expiryTimer;

  /// Whether a server-confirmed fair-use cooldown is persisted, including an
  /// expired one that still needs authoritative reconciliation before retry.
  bool get hasPersistedFairUseState =>
      SharedPreferencesUtil().getString(_prefKeyReason) == RateLimitReason.fairUse.name &&
      SharedPreferencesUtil().getInt(_prefKeyUntil) > 0;

  bool get isFairUseLimited {
    if (!hasPersistedFairUseState) return false;
    final until = SharedPreferencesUtil().getInt(_prefKeyUntil);
    return until > DateTime.now().millisecondsSinceEpoch;
  }

  bool get isBackendBusyLimited => _backendBusyUntilMs > DateTime.now().millisecondsSinceEpoch;

  bool get isBackfillLimited =>
      SharedPreferencesUtil().getInt(_prefKeyBackfillUntil) > DateTime.now().millisecondsSinceEpoch;

  bool isLimitedForLane(String lane) {
    if (isBackendBusyLimited) return true;
    return lane == 'backfill' ? isBackfillLimited : isFairUseLimited;
  }

  bool get isLimited {
    final now = DateTime.now().millisecondsSinceEpoch;
    if (_backendBusyUntilMs > now) return true;
    return isFairUseLimited || isBackfillLimited;
  }

  DateTime? get until {
    final now = DateTime.now().millisecondsSinceEpoch;
    final persisted = hasPersistedFairUseState ? SharedPreferencesUtil().getInt(_prefKeyUntil) : 0;
    final inMemory = _backendBusyUntilMs;
    final backfill = SharedPreferencesUtil().getInt(_prefKeyBackfillUntil);
    final candidates = <int>[
      if (inMemory > now) inMemory,
      if (persisted > now) persisted,
      if (backfill > now) backfill,
    ];
    if (candidates.isEmpty) return null;
    return DateTime.fromMillisecondsSinceEpoch(candidates.reduce((a, b) => a > b ? a : b));
  }

  RateLimitReason? get reason {
    final now = DateTime.now().millisecondsSinceEpoch;
    final persisted = hasPersistedFairUseState ? SharedPreferencesUtil().getInt(_prefKeyUntil) : 0;
    final busyActive = _backendBusyUntilMs > now;
    final rateActive = persisted > now;
    final backfill = SharedPreferencesUtil().getInt(_prefKeyBackfillUntil);
    final backfillActive = backfill > now;
    if (!busyActive && !rateActive && !backfillActive) return null;
    // Match `until`'s max-based pick so reason and deadline refer to the same cooldown.
    if (busyActive && _backendBusyUntilMs >= persisted && _backendBusyUntilMs >= backfill) {
      return RateLimitReason.backendBusy;
    }
    if (backfillActive && backfill >= persisted && backfill >= _backendBusyUntilMs) {
      return RateLimitReason.backfillPaced;
    }
    return RateLimitReason.fairUse;
  }

  /// Pause uploads. Honors the server's Retry-After (seconds) when present,
  /// otherwise falls back to a 30-minute cooldown. [reason] picks the
  /// user-facing message ("Fair-use limit reached" vs "Backend busy") and
  /// also picks the persistence mode (fairUse persists, backendBusy is
  /// in-memory only).
  void markLimited({int? retryAfterSeconds, RateLimitReason reason = RateLimitReason.fairUse}) {
    final requested = (retryAfterSeconds != null && retryAfterSeconds > 0)
        ? retryAfterSeconds
        : _defaultCooldownSeconds;
    final maxCooldown = reason == RateLimitReason.fairUse ? _maxFairUseCooldownSeconds : _maxBackendBusyCooldownSeconds;
    final secs = requested > maxCooldown ? maxCooldown : requested;
    final untilMs = DateTime.now().add(Duration(seconds: secs)).millisecondsSinceEpoch;
    if (reason == RateLimitReason.backendBusy) {
      _backendBusyUntilMs = untilMs;
    } else if (reason == RateLimitReason.backfillPaced) {
      SharedPreferencesUtil().saveInt(_prefKeyBackfillUntil, untilMs);
    } else {
      SharedPreferencesUtil().saveInt(_prefKeyUntil, untilMs);
      SharedPreferencesUtil().saveString(_prefKeyReason, reason.name);
    }
    _scheduleExpiryNotification();
    notifyListeners();
  }

  int? get activeRetryAfterSeconds {
    final deadline = until;
    if (deadline == null) return null;
    final remainingMs = deadline.millisecondsSinceEpoch - DateTime.now().millisecondsSinceEpoch;
    if (remainingMs <= 0) return null;
    return (remainingMs / 1000).ceil();
  }

  /// Clear the cooldown after any successful upload.
  void clear() {
    _backendBusyUntilMs = 0;
    SharedPreferencesUtil().saveInt(_prefKeyUntil, 0);
    SharedPreferencesUtil().saveString(_prefKeyReason, '');
    SharedPreferencesUtil().saveInt(_prefKeyBackfillUntil, 0);
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

  void clearForLane(String lane) {
    _backendBusyUntilMs = 0;
    if (lane == 'backfill') {
      SharedPreferencesUtil().saveInt(_prefKeyBackfillUntil, 0);
    } else {
      SharedPreferencesUtil().saveInt(_prefKeyUntil, 0);
      SharedPreferencesUtil().saveString(_prefKeyReason, '');
    }
    _scheduleExpiryNotification();
    notifyListeners();
  }

  void _scheduleExpiryNotification() {
    _expiryTimer?.cancel();
    final now = DateTime.now().millisecondsSinceEpoch;
    final deadlines = <int>[
      if (_backendBusyUntilMs > now) _backendBusyUntilMs,
      if (SharedPreferencesUtil().getInt(_prefKeyBackfillUntil) > now)
        SharedPreferencesUtil().getInt(_prefKeyBackfillUntil),
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
