import 'dart:async';
import 'dart:math';

import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_result.dart';

/// Endpoint-owned retries. Pool retries stay disabled so they cannot bypass
/// Retry-After. Auth replay remains owned by shared.dart.
class ReadRetry {
  ReadRetry({Future<void> Function(Duration)? wait, DateTime Function()? now, double Function()? random})
    : _wait = wait,
      now = now ?? DateTime.now,
      random = random ?? Random().nextDouble;

  static const callerWindow = Duration(seconds: 10); // Siri's smallest caller timeout.
  final Future<void> Function(Duration)? _wait;
  final DateTime Function() now;
  final double Function() random;
  final _closed = Completer<void>();
  final _timers = <Timer, Completer<bool>>{};

  bool get isClosed => _closed.isCompleted;

  ReadRetry newSession() => ReadRetry(wait: _wait, now: now, random: random);

  /// Cancel real backoff timers and wake any waiting request without replaying.
  void close() {
    if (_closed.isCompleted) return;
    _closed.complete();
    for (final entry in _timers.entries) {
      entry.key.cancel();
      entry.value.complete(false);
    }
    _timers.clear();
  }

  Future<bool> _pause(Duration delay) async {
    if (_closed.isCompleted) return false;
    final wait = _wait;
    if (wait != null) {
      return Future.any([wait(delay).then((_) => true), _closed.future.then((_) => false)]);
    }
    final done = Completer<bool>();
    late final Timer timer;
    timer = Timer(delay, () {
      _timers.remove(timer);
      done.complete(true);
    });
    _timers[timer] = done;
    return done.future;
  }

  /// Three attempts within the caller-visible deadline, including requests and
  /// reporting. Reserve at least one second (or the last observed request time)
  /// for a retry to finish; never shorten Retry-After to squeeze one in.
  Future<http.Response?> run(
    Future<http.Response?> Function(Duration timeout) send, {
    required Future<void> Function(http.Response) onRetry,
    DateTime? deadline,
  }) async {
    final end = deadline ?? now().add(callerWindow);
    http.Response? lastResponse;
    for (var attempt = 0; ; attempt++) {
      final started = now();
      final remaining = end.difference(started);
      if (_closed.isCompleted || remaining <= Duration.zero) return lastResponse;
      final response = await send(
        remaining,
      ).then<http.Response?>((value) => value).timeout(remaining, onTimeout: () => null);
      final requestTime = now().difference(started);
      lastResponse = response;
      if (_closed.isCompleted ||
          response == null ||
          (response.statusCode != 429 && response.statusCode != 503) ||
          attempt == 2) {
        return response;
      }
      final completionReserve = requestTime > const Duration(seconds: 1) ? requestTime : const Duration(seconds: 1);
      final backoff = Duration(milliseconds: 1000 * (1 << attempt) + (random() * 250).floor());
      final serverDelay = parseApiRetryAfter(response, now);
      final delay = serverDelay != null && serverDelay > backoff ? serverDelay : backoff;
      bool fits() => now().add(delay + completionReserve).isBefore(end);
      if (!fits()) return response;
      await onRetry(response);
      // Reporting is part of the caller window too. Recheck after every await.
      if (_closed.isCompleted || !fits()) return response;
      if (!await _pause(delay)) return response;
      if (_closed.isCompleted || !now().add(completionReserve).isBefore(end)) return response;
    }
  }
}
