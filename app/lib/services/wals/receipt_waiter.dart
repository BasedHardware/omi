import 'dart:async';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/services/wals/sync_job_poller.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/reliability_experiments.dart';

/// A foreground subscription to the accepted jobs on one phone/account generation.
/// The persisted WAL inventory is the acknowledgement: an interrupted wait can
/// always be repeated. Unavailable handles use the existing paced GET recovery.
class ReceiptWaiter {
  ReceiptWaiter({required this.jobs, required this.apply, this.fetch = waitForSyncReceipts});

  final Set<String> Function() jobs;
  final Future<void> Function(Map<String, SyncJobFetch>) apply;
  final Future<SyncReceiptBatch> Function(List<String>, Future<void>) fetch;
  final _fallback = <String>{};
  final _starts = <DateTime>[];
  Set<String> _known = {};
  Completer<void>? _cancel;
  Timer? _retry;
  bool _running = false;
  bool _stopped = false;
  bool _useLegacy = false;
  int _offset = 0;

  static bool get _on => ReliabilityExperiments.enabled('receipt_long_poll');

  bool handles(String id) => _on && !_stopped && !_useLegacy && !_fallback.contains(id);

  void refresh() {
    // Off, a waiter never opens a request and no job leaves the GET polling.
    if (_stopped || !_on) return;
    final next = jobs();
    _fallback.removeWhere((id) => !next.contains(id));
    final cancel = _cancel;
    if (cancel != null && !cancel.isCompleted && (next.isEmpty || next.difference(_known).isNotEmpty)) {
      cancel.complete();
      _offset = 0;
    }
    _known = next;
    if (_running || _retry != null || next.isEmpty) return;
    _running = true;
    unawaited(_run());
  }

  Future<void> _run() async {
    try {
      while (!_stopped && _on) {
        final candidates = jobs().where((id) => !_fallback.contains(id)).toList();
        if (candidates.isEmpty) break;
        final now = DateTime.now();
        _starts.removeWhere((at) => now.difference(at) >= const Duration(minutes: 1));
        final cooldown = SyncRateLimiter.instance.activeRetryAfterSeconds;
        if (cooldown != null || _starts.length >= SyncJobPoller.maxRequestsPerMinute) {
          _pause(cooldown != null
              ? Duration(seconds: cooldown)
              : _starts.first.add(const Duration(minutes: 1)).difference(now));
          break;
        }
        final selected =
            List.generate(candidates.length.clamp(1, 16), (i) => candidates[(_offset + i) % candidates.length]);
        final cancel = Completer<void>();
        _cancel = cancel;
        _starts.add(now);
        try {
          final response = await fetch(selected, cancel.future);
          if (_stopped || cancel.isCompleted) continue;
          _cancel = null;
          _fallback.addAll(response.fallback);
          _offset = (_offset + selected.length) % candidates.length;
          if (response.receipts.isNotEmpty) await apply(response.receipts);
        } catch (error) {
          if (_stopped || cancel.isCompleted) continue;
          if (error is SyncRateLimitedException) {
            SyncRateLimiter.instance
                .markLimited(retryAfterSeconds: error.retryAfterSeconds, reason: error.kind.cooldownReason);
          }
          Logger.debug('Receipt wait unavailable: ${error.runtimeType}');
          _useLegacy = true;
          _pause(const Duration(seconds: 30));
          break;
        } finally {
          _cancel = null;
        }
      }
    } finally {
      _running = false;
    }
  }

  void _pause(Duration delay) {
    _retry = Timer(delay, () {
      _retry = null;
      _useLegacy = false;
      refresh();
    });
  }

  void stop() {
    _stopped = true;
    _retry?.cancel();
    if (_cancel != null && !_cancel!.isCompleted) _cancel!.complete();
  }
}
