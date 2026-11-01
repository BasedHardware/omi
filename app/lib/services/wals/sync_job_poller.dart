import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';

/// Account-wide request admission shared by WAL and Transcribe Later polling.
/// Wake coalescing bounds concurrency, but cannot bound requests over time.
/// Durable first-404 observations, so missing-job confirmation survives app
/// restarts. Without it a large dead backlog is re-polled from scratch in every
/// process and never confirmed (2026-10 expiry-retired handles).
abstract class SyncJobMissingStore {
  Map<String, int> load();
  void save(Map<String, int> firstMissingEpochMs);
}

class PreferencesSyncJobMissingStore implements SyncJobMissingStore {
  static const key = 'syncJobFirstMissingV1';

  @override
  Map<String, int> load() {
    try {
      final raw = SharedPreferencesUtil().getString(key);
      if (raw.isEmpty) return {};
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return {};
      return {
        for (final e in decoded.entries)
          if (e.key is String && e.value is int) e.key as String: e.value as int,
      };
    } catch (_) {
      return {};
    }
  }

  @override
  void save(Map<String, int> firstMissingEpochMs) {
    try {
      SharedPreferencesUtil().saveString(key, jsonEncode(firstMissingEpochMs));
    } catch (_) {
      // Persistence is an optimization: in-memory confirmation still works.
    }
  }
}

class SyncJobPoller {
  SyncJobPoller({DateTime Function()? clock, SyncRateLimiter? limiter, SyncJobMissingStore? missingStore})
      : _clock = clock ?? DateTime.now,
        _limiter = limiter ?? SyncRateLimiter.instance,
        _missingStore = missingStore;

  static final instance = SyncJobPoller();
  static const maxRequestsPerMinute = 18;
  static const minimumInterval = Duration(seconds: 20);
  static const missingConfirmationInterval = Duration(minutes: 5);
  static const missingRetention = Duration(days: 7);
  static const maxPersistedMissing = 20000;
  static const recentUploadWindow = Duration(hours: 24);
  DateTime Function() _clock;
  final SyncRateLimiter _limiter;
  SyncJobMissingStore? _missingStore;
  final List<DateTime> _requests = [];
  final Map<String, DateTime> _nextPoll = {};
  final Set<String> _inFlight = {};
  final Map<String, DateTime> _missing = {};
  final Set<String> _confirmedMissing = {};
  bool _missingLoaded = false;

  /// Enables durable missing-job confirmation; the app singleton opts in at
  /// startup so isolated pollers in tests stay hermetic.
  void persistMissingWith(SyncJobMissingStore store) {
    _missingStore = store;
    _missingLoaded = false;
  }

  void _loadMissing() {
    if (_missingLoaded) return;
    _missingLoaded = true;
    final store = _missingStore;
    if (store == null) return;
    final cutoff = _clock().subtract(missingRetention);
    for (final e in store.load().entries) {
      final seen = DateTime.fromMillisecondsSinceEpoch(e.value);
      if (seen.isBefore(cutoff) || _missing.containsKey(e.key)) continue;
      _missing[e.key] = seen;
      final due = seen.add(missingConfirmationInterval);
      if (due.isAfter(_nextPoll[e.key] ?? DateTime(1970))) _nextPoll[e.key] = due;
    }
  }

  void _saveMissing() {
    final store = _missingStore;
    if (store == null) return;
    final cutoff = _clock().subtract(missingRetention);
    final kept = _missing.entries.where((e) => !e.value.isBefore(cutoff)).toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    store.save({for (final e in kept.take(maxPersistedMissing)) e.key: e.value.millisecondsSinceEpoch});
  }

  /// Job ids are immutable. Never adopt an owner already proven expired in this
  /// session, even when an older server returns it again with a 409.
  void validateOwner(UploadFilesResult result) {
    if (_confirmedMissing.contains(result.jobId)) {
      throw SyncRateLimitedException(
        kind: SyncRateLimitKind.edgeThrottle,
        retryAfterSeconds: 60,
        reasonCode: 'sync_content_in_progress',
      );
    }
  }

  @visibleForTesting
  void resetForTesting({DateTime Function()? clock}) {
    assert(_inFlight.isEmpty && !_passRunning);
    _clock = clock ?? DateTime.now;
    _requests.clear();
    _nextPoll.clear();
    _missing.clear();
    _confirmedMissing.clear();
    _missingStore = null;
    _missingLoaded = false;
  }

  bool _passRunning = false;

  bool beginPass() {
    if (_passRunning || _limiter.isLimited) return false;
    _passRunning = true;
    return true;
  }

  void endPass() => _passRunning = false;

  /// Admission order for one reconcile pass.
  ///
  /// A handle whose first 404 is old enough to confirm goes first: one request
  /// retires it for good. Then recent uploads (within [recentUploadWindow]) and
  /// older handles alternate, so a large dead backlog can neither starve fresh
  /// uploads nor be starved by them. Within each class the least recently due
  /// goes first, ties by newest upload, then id. Callers without upload times
  /// keep the oldest-due-first order.
  List<String> ordered(Iterable<String> jobs, {Map<String, int>? uploadedAtSeconds}) {
    _loadMissing();
    final now = _clock();
    final cutoff = now.subtract(const Duration(days: 1));
    _nextPoll.removeWhere(
      (id, deadline) => deadline.isBefore(cutoff) && !_inFlight.contains(id) && !_missing.containsKey(id),
    );
    final epoch = DateTime(1970);
    int uploaded(String id) => uploadedAtSeconds?[id] ?? 0;
    bool confirmable(String id) {
      final seen = _missing[id];
      return seen != null && !now.isBefore(seen.add(missingConfirmationInterval));
    }

    int compare(String a, String b) {
      final ca = confirmable(a), cb = confirmable(b);
      if (ca != cb) return ca ? -1 : 1;
      final due = (_nextPoll[a] ?? epoch).compareTo(_nextPoll[b] ?? epoch);
      if (due != 0) return due;
      final recency = uploaded(b).compareTo(uploaded(a));
      return recency != 0 ? recency : a.compareTo(b);
    }

    final all = jobs.toList();
    if (uploadedAtSeconds == null) return all..sort(compare);
    final recentFloor = now.subtract(recentUploadWindow).millisecondsSinceEpoch ~/ 1000;
    final confirm = all.where(confirmable).toList()..sort(compare);
    final rest = all.where((id) => !confirmable(id));
    final recent = rest.where((id) => uploaded(id) >= recentFloor).toList()..sort(compare);
    final older = rest.where((id) => uploaded(id) < recentFloor).toList()..sort(compare);
    final out = <String>[...confirm];
    for (var i = 0; i < recent.length || i < older.length; i++) {
      if (i < recent.length) out.add(recent[i]);
      if (i < older.length) out.add(older[i]);
    }
    return out;
  }

  void defer(String jobId, int milliseconds) {
    final deadline = _clock().add(Duration(milliseconds: milliseconds < 20000 ? 20000 : milliseconds));
    if (deadline.isAfter(_nextPoll[jobId] ?? DateTime(1970))) _nextPoll[jobId] = deadline;
  }

  /// A bounded batch of jobs this pass can actually poll. Skipping locally
  /// deferred jobs avoids thousands of no-op futures and misleading transient
  /// diagnostics while preserving the ordering and backoff used by [fetch].
  List<String> dueForPass(Iterable<String> jobs, {Map<String, int>? uploadedAtSeconds}) {
    final now = _clock();
    _requests.removeWhere((time) => !time.isAfter(now.subtract(const Duration(minutes: 1))));
    if (_limiter.isLimited || _requests.length >= maxRequestsPerMinute) return const [];
    return ordered(jobs, uploadedAtSeconds: uploadedAtSeconds)
        .where((id) => !_inFlight.contains(id) && !now.isBefore(_nextPoll[id] ?? DateTime(1970)))
        .take(maxRequestsPerMinute - _requests.length)
        .toList();
  }

  Future<SyncJobFetch> fetch(String jobId, Future<SyncJobFetch> Function(String) fetcher) async {
    _loadMissing();
    final now = _clock();
    _requests.removeWhere((time) => !time.isAfter(now.subtract(const Duration(minutes: 1))));
    if (_limiter.isLimited ||
        _inFlight.contains(jobId) ||
        now.isBefore(_nextPoll[jobId] ?? DateTime(1970)) ||
        _requests.length >= maxRequestsPerMinute) {
      return const SyncJobFetch.deferred();
    }
    // Reserve before awaiting, including failed requests and overlapping owners.
    _requests.add(now);
    _inFlight.add(jobId);
    defer(jobId, minimumInterval.inMilliseconds);
    try {
      final fetch = await fetcher(jobId);
      switch (fetch.outcome) {
        case SyncJobFetchOutcome.throttled:
          final limit = fetch.rateLimit!;
          _limiter.markLimited(retryAfterSeconds: limit.retryAfterSeconds, reason: limit.kind.cooldownReason);
          break;
        case SyncJobFetchOutcome.notFound:
          final firstSeen = _missing[jobId];
          if (firstSeen == null || now.isBefore(firstSeen.add(missingConfirmationInterval))) {
            // A single missing read is not proof that processing stopped. The
            // first observation is durable, so a later process can confirm it.
            _missing.putIfAbsent(jobId, () => now);
            if (firstSeen == null) _saveMissing();
            defer(jobId, missingConfirmationInterval.inMilliseconds);
            return const SyncJobFetch.missingConfirmation();
          }
          _missing.remove(jobId);
          _confirmedMissing.add(jobId);
          _saveMissing();
          break;
        case SyncJobFetchOutcome.transient:
          defer(jobId, const Duration(minutes: 1).inMilliseconds);
          break;
        case SyncJobFetchOutcome.ok:
          if (_missing.remove(jobId) != null) _saveMissing();
          defer(jobId, fetch.status?.pollAfterMs ?? 20000);
          break;
      }
      return fetch;
    } catch (_) {
      defer(jobId, const Duration(minutes: 1).inMilliseconds);
      rethrow;
    } finally {
      _inFlight.remove(jobId);
    }
  }
}

extension SyncRateLimitCooldown on SyncRateLimitKind {
  RateLimitReason get cooldownReason => switch (this) {
        SyncRateLimitKind.fairUse => RateLimitReason.fairUse,
        SyncRateLimitKind.backendCapacity => RateLimitReason.backendBusy,
        SyncRateLimitKind.edgeThrottle => RateLimitReason.edgeThrottle,
      };
}
