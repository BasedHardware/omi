import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';

/// Account-wide request admission shared by WAL and Transcribe Later polling.
/// Wake coalescing bounds concurrency, but cannot bound requests over time.
class SyncJobPoller {
  SyncJobPoller({DateTime Function()? clock, SyncRateLimiter? limiter})
      : _clock = clock ?? DateTime.now,
        _limiter = limiter ?? SyncRateLimiter.instance;

  static final instance = SyncJobPoller();
  static const maxRequestsPerMinute = 18;
  static const minimumInterval = Duration(seconds: 20);
  static const missingConfirmationInterval = Duration(minutes: 5);
  final DateTime Function() _clock;
  final SyncRateLimiter _limiter;
  final List<DateTime> _requests = [];
  final Map<String, DateTime> _nextPoll = {};
  final Set<String> _inFlight = {};
  final Set<String> _missing = {};
  bool _passRunning = false;

  bool beginPass() {
    if (_passRunning || _limiter.isLimited) return false;
    _passRunning = true;
    return true;
  }

  void endPass() => _passRunning = false;

  /// Oldest due jobs go first so large backlogs cannot starve behind job #1.
  List<String> ordered(Iterable<String> jobs) {
    final cutoff = _clock().subtract(const Duration(days: 1));
    _nextPoll.removeWhere((id, deadline) => deadline.isBefore(cutoff) && !_inFlight.contains(id));
    _missing.removeWhere((id) => !_nextPoll.containsKey(id));
    return jobs.toList()
      ..sort((a, b) {
        final age = (_nextPoll[a] ?? DateTime(1970)).compareTo(_nextPoll[b] ?? DateTime(1970));
        return age != 0 ? age : a.compareTo(b);
      });
  }

  void defer(String jobId, int milliseconds) {
    final deadline = _clock().add(Duration(milliseconds: milliseconds < 20000 ? 20000 : milliseconds));
    if (deadline.isAfter(_nextPoll[jobId] ?? DateTime(1970))) _nextPoll[jobId] = deadline;
  }

  Future<SyncJobFetch> fetch(String jobId, Future<SyncJobFetch> Function(String) fetcher) async {
    final now = _clock();
    _requests.removeWhere((time) => !time.isAfter(now.subtract(const Duration(minutes: 1))));
    if (_limiter.isLimited ||
        _inFlight.contains(jobId) ||
        now.isBefore(_nextPoll[jobId] ?? DateTime(1970)) ||
        _requests.length >= maxRequestsPerMinute) {
      return const SyncJobFetch(SyncJobFetchOutcome.transient);
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
          if (_missing.add(jobId)) {
            // A single missing Redis read is not proof that processing stopped.
            defer(jobId, missingConfirmationInterval.inMilliseconds);
            return const SyncJobFetch(SyncJobFetchOutcome.transient);
          }
          _missing.remove(jobId);
          break;
        case SyncJobFetchOutcome.transient:
          defer(jobId, const Duration(minutes: 1).inMilliseconds);
          break;
        case SyncJobFetchOutcome.ok:
          _missing.remove(jobId);
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
