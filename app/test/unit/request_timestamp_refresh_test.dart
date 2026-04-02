import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/shared.dart';

/// Tests that _buildRequest() refreshes X-Request-Start-Time on each call,
/// ensuring retries and pool-queued requests don't send stale timestamps.
///
/// Uses buildRequestForTest() which is a @visibleForTesting wrapper around
/// the real production _buildRequest() in shared.dart.

void main() {
  group('_buildRequest timestamp refresh', () {
    test('each call produces a fresh X-Request-Start-Time', () async {
      final headers = <String, String>{
        'X-Request-Start-Time': '1000000000.0',
        'Authorization': 'Bearer test-token',
      };

      final request1 = buildRequestForTest('https://api.example.com/v1/test', headers, '', 'GET');
      final ts1 = double.parse(request1.headers['X-Request-Start-Time']!);

      // Small delay to ensure timestamps differ
      await Future.delayed(const Duration(milliseconds: 10));

      final request2 = buildRequestForTest('https://api.example.com/v1/test', headers, '', 'GET');
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

      buildRequestForTest('https://api.example.com/v1/test', headers, '{}', 'POST');

      // The original map should still have the old timestamp
      expect(headers['X-Request-Start-Time'], '1000000000.0');
    });

    test('stale timestamp in headers is overridden on each build', () {
      final staleTimestamp = '1000000000.0'; // year 2001
      final headers = <String, String>{
        'X-Request-Start-Time': staleTimestamp,
      };

      final request = buildRequestForTest('https://api.example.com/v1/test', headers, '', 'GET');

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
      http.Request requestBuilder() => buildRequestForTest('https://api.example.com/v1/test', headers, '', 'PATCH');

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
