import 'dart:async';
import 'dart:math';

import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_result.dart';

/// Endpoint-owned retry policy. Callers disable pool retries to avoid replaying
/// a 503 before its Retry-After deadline. Auth replay remains owned by shared.dart.
class ReadRetry {
  ReadRetry({Future<void> Function(Duration)? wait, DateTime Function()? now, double Function()? random})
      : wait = wait ?? Future<void>.delayed,
        now = now ?? DateTime.now,
        random = random ?? Random().nextDouble;

  final Future<void> Function(Duration) wait;
  final DateTime Function() now;
  final double Function() random;

  /// Three attempts, at most ten seconds spent waiting. If the server asks for
  /// longer, return the failure for manual retry instead of retrying too early.
  Future<http.Response?> run(
    Future<http.Response?> Function() send, {
    required Future<void> Function(http.Response) onRetry,
  }) async {
    var remainingWait = const Duration(seconds: 10);
    for (var attempt = 0;; attempt++) {
      final response = await send();
      if (response == null || (response.statusCode != 429 && response.statusCode != 503) || attempt == 2) {
        return response;
      }
      final backoff = Duration(milliseconds: 1000 * (1 << attempt) + (random() * 250).floor());
      final serverDelay = parseApiRetryAfter(response, now);
      final delay = serverDelay != null && serverDelay > backoff ? serverDelay : backoff;
      if (delay > remainingWait) return response;
      await onRetry(response);
      await wait(delay);
      remainingWait -= delay;
    }
  }
}
