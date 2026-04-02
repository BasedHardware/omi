import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

/// Tests that _buildRequest() refreshes X-Request-Start-Time on each call,
/// ensuring retries and pool-queued requests don't send stale timestamps.
///
/// _buildRequest() is private (underscore) in shared.dart and depends on
/// non-injectable singletons (HttpPoolManager, SharedPreferencesUtil,
/// AuthService), so this test mirrors the exact request-building logic via
/// a minimal abstraction — the same pattern used by multipart_401_retry_test.dart.

/// Mirrors _buildRequest() from shared.dart:157 — builds an http.Request
/// and stamps a fresh X-Request-Start-Time on the request object.
/// IMPORTANT: keep this in sync with the production _buildRequest().
http.Request buildRequest(String url, Map<String, String> headers, String body, String method) {
  final request = http.Request(method, Uri.parse(url));
  request.headers.addAll(headers);
  // Refresh timestamp on each request build so retries and pool-queued
  // requests don't send a stale X-Request-Start-Time (#6274)
  request.headers['X-Request-Start-Time'] = (DateTime.now().millisecondsSinceEpoch / 1000).toString();
  if (method != 'GET' && body.isNotEmpty) {
    request.headers['Content-Type'] = 'application/json';
    request.body = body;
  }
  return request;
}

void main() {
  group('_buildRequest timestamp refresh', () {
    test('each call produces a fresh X-Request-Start-Time', () async {
      final headers = <String, String>{
        'X-Request-Start-Time': '1000000000.0',
        'Authorization': 'Bearer test-token',
      };

      final request1 = buildRequest('https://api.example.com/v1/test', headers, '', 'GET');
      final ts1 = double.parse(request1.headers['X-Request-Start-Time']!);

      // Small delay to ensure timestamps differ
      await Future.delayed(const Duration(milliseconds: 10));

      final request2 = buildRequest('https://api.example.com/v1/test', headers, '', 'GET');
      final ts2 = double.parse(request2.headers['X-Request-Start-Time']!);

      // Both timestamps should be recent (not the stale 1000000000.0)
      expect(ts1, greaterThan(1700000000.0));
      expect(ts2, greaterThan(1700000000.0));

      // Second call should have equal or later timestamp
      expect(ts2, greaterThanOrEqualTo(ts1));
    });

    test('does not mutate the caller-supplied headers map', () {
      final headers = <String, String>{
        'X-Request-Start-Time': '1000000000.0',
        'Authorization': 'Bearer test-token',
      };

      buildRequest('https://api.example.com/v1/test', headers, '{}', 'POST');

      // The original map should still have the old timestamp
      expect(headers['X-Request-Start-Time'], '1000000000.0');
    });

    test('stale timestamp in headers is overridden on each build', () {
      final staleTimestamp = '1000000000.0'; // year 2001
      final headers = <String, String>{
        'X-Request-Start-Time': staleTimestamp,
      };

      final request = buildRequest('https://api.example.com/v1/test', headers, '', 'GET');

      // Request should have a fresh timestamp, not the stale one
      expect(request.headers['X-Request-Start-Time'], isNot(staleTimestamp));
      final ts = double.parse(request.headers['X-Request-Start-Time']!);
      expect(ts, greaterThan(1700000000.0));
    });

    test('simulated retry loop gets fresh timestamps', () async {
      final headers = <String, String>{
        'X-Request-Start-Time': '1000000000.0',
      };

      // Simulate requestBuilder closure as used in makeApiCall
      http.Request requestBuilder() => buildRequest('https://api.example.com/v1/test', headers, '', 'PATCH');

      final timestamps = <double>[];
      for (var i = 0; i <= 2; i++) {
        final request = requestBuilder();
        timestamps.add(double.parse(request.headers['X-Request-Start-Time']!));
        if (i < 2) {
          await Future.delayed(const Duration(milliseconds: 10));
        }
      }

      // All timestamps should be recent
      for (final ts in timestamps) {
        expect(ts, greaterThan(1700000000.0));
      }

      // Each subsequent timestamp should be >= previous
      for (var i = 1; i < timestamps.length; i++) {
        expect(timestamps[i], greaterThanOrEqualTo(timestamps[i - 1]));
      }
    });
  });
}
