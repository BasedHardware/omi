import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

/// Tests the clock skew 408 detection logic used in shared.dart.
///
/// The production code uses singletons (MyApp, AppSnackbar) that aren't
/// injectable, so this test exercises the parsing and rate-limiting logic
/// via a minimal abstraction that mirrors the production flow.

/// Mirrors _ClockSkewResponse from shared.dart.
class ClockSkewResponse {
  final String? serverTime;
  final String? clientTime;
  final int skewSeconds;
  final String? hint;

  const ClockSkewResponse({
    required this.serverTime,
    required this.clientTime,
    required this.skewSeconds,
    required this.hint,
  });
}

/// Mirrors _parseInt from shared.dart.
int? parseInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.round();
  if (value is String) return int.tryParse(value);
  return null;
}

/// Mirrors _parseClockSkewResponse from shared.dart.
ClockSkewResponse? parseClockSkewResponse(http.Response response) {
  if (response.statusCode != 408 || response.body.isEmpty) {
    return null;
  }

  final contentType = response.headers['content-type']?.toLowerCase() ?? '';
  if (!contentType.contains('json')) {
    return null;
  }

  try {
    final dynamic decoded = jsonDecode(response.body);
    if (decoded is! Map) {
      return null;
    }
    final responseMap = decoded.map((key, value) => MapEntry(key.toString(), value));
    if (responseMap['error']?.toString() != 'clock_skew') {
      return null;
    }

    final skewSeconds = parseInt(responseMap['skew_seconds']);
    if (skewSeconds == null) {
      return null;
    }

    return ClockSkewResponse(
      serverTime: responseMap['server_time']?.toString(),
      clientTime: responseMap['client_time']?.toString(),
      skewSeconds: skewSeconds,
      hint: responseMap['hint']?.toString(),
    );
  } catch (_) {
    return null;
  }
}

/// Mirrors _toSkewMinutes from shared.dart.
int toSkewMinutes(int skewSeconds) {
  final minutes = (skewSeconds.abs() / 60).ceil();
  return minutes == 0 ? 1 : minutes;
}

/// Mirrors rate-limiting logic from _checkClockSkewResponse in shared.dart.
class SnackbarRateLimiter {
  static const Duration cooldown = Duration(seconds: 45);
  DateTime? _lastShownAt;

  bool shouldShow() {
    final now = DateTime.now();
    if (_lastShownAt != null && now.difference(_lastShownAt!) < cooldown) {
      return false;
    }
    _lastShownAt = now;
    return true;
  }
}

http.Response _make408({required String body, String contentType = 'application/json'}) {
  return http.Response(body, 408, headers: {'content-type': contentType});
}

http.Response _make200() {
  return http.Response('ok', 200);
}

void main() {
  group('parseClockSkewResponse', () {
    test('parses valid clock_skew 408 JSON', () {
      final response = _make408(
        body: jsonEncode({
          'error': 'clock_skew',
          'server_time': 1774240978.08,
          'client_time': 1774240078.07,
          'skew_seconds': 900.0,
          'hint': 'Check your device date/time settings',
        }),
      );
      final result = parseClockSkewResponse(response);
      expect(result, isNotNull);
      expect(result!.skewSeconds, 900);
      expect(result.serverTime, '1774240978.08');
      expect(result.clientTime, '1774240078.07');
      expect(result.hint, 'Check your device date/time settings');
    });

    test('returns null for non-408 status', () {
      final response = http.Response(
        jsonEncode({'error': 'clock_skew', 'skew_seconds': 900}),
        200,
        headers: {'content-type': 'application/json'},
      );
      expect(parseClockSkewResponse(response), isNull);
    });

    test('returns null for empty body', () {
      final response = _make408(body: '');
      expect(parseClockSkewResponse(response), isNull);
    });

    test('returns null for non-JSON content-type', () {
      final response = _make408(body: 'Request Timeout', contentType: 'text/plain');
      expect(parseClockSkewResponse(response), isNull);
    });

    test('returns null for HTML content-type (proxy 408)', () {
      final response = _make408(body: '<html>timeout</html>', contentType: 'text/html');
      expect(parseClockSkewResponse(response), isNull);
    });

    test('returns null for malformed JSON', () {
      final response = _make408(body: '{not valid json}');
      expect(parseClockSkewResponse(response), isNull);
    });

    test('returns null when error is not clock_skew', () {
      final response = _make408(
        body: jsonEncode({'error': 'timeout', 'skew_seconds': 900}),
      );
      expect(parseClockSkewResponse(response), isNull);
    });

    test('returns null when error field is missing', () {
      final response = _make408(
        body: jsonEncode({'skew_seconds': 900}),
      );
      expect(parseClockSkewResponse(response), isNull);
    });

    test('returns null when skew_seconds is missing', () {
      final response = _make408(
        body: jsonEncode({'error': 'clock_skew'}),
      );
      expect(parseClockSkewResponse(response), isNull);
    });

    test('returns null when skew_seconds is non-numeric string', () {
      final response = _make408(
        body: jsonEncode({'error': 'clock_skew', 'skew_seconds': 'abc'}),
      );
      expect(parseClockSkewResponse(response), isNull);
    });

    test('handles integer skew_seconds', () {
      final response = _make408(
        body: jsonEncode({'error': 'clock_skew', 'skew_seconds': 900}),
      );
      final result = parseClockSkewResponse(response);
      expect(result, isNotNull);
      expect(result!.skewSeconds, 900);
    });

    test('rounds float skew_seconds to int', () {
      final response = _make408(
        body: jsonEncode({'error': 'clock_skew', 'skew_seconds': 899.7}),
      );
      final result = parseClockSkewResponse(response);
      expect(result, isNotNull);
      expect(result!.skewSeconds, 900);
    });

    test('handles case-insensitive content-type', () {
      final response = http.Response(
        jsonEncode({'error': 'clock_skew', 'skew_seconds': 300}),
        408,
        headers: {'content-type': 'Application/JSON; charset=utf-8'},
      );
      final result = parseClockSkewResponse(response);
      expect(result, isNotNull);
      expect(result!.skewSeconds, 300);
    });

    test('returns null for non-200 non-408 status', () {
      final response = http.Response(
        jsonEncode({'error': 'clock_skew', 'skew_seconds': 900}),
        500,
        headers: {'content-type': 'application/json'},
      );
      expect(parseClockSkewResponse(response), isNull);
    });
  });

  group('toSkewMinutes', () {
    test('converts seconds to minutes (ceiling)', () {
      expect(toSkewMinutes(900), 15);
      expect(toSkewMinutes(300), 5);
      expect(toSkewMinutes(301), 6); // ceiling rounds up
    });

    test('minimum 1 minute', () {
      expect(toSkewMinutes(0), 1);
      expect(toSkewMinutes(1), 1);
      expect(toSkewMinutes(59), 1);
    });

    test('handles negative skew (abs value)', () {
      expect(toSkewMinutes(-900), 15);
      expect(toSkewMinutes(-1), 1);
    });
  });

  group('SnackbarRateLimiter', () {
    test('allows first call', () {
      final limiter = SnackbarRateLimiter();
      expect(limiter.shouldShow(), isTrue);
    });

    test('blocks immediate second call', () {
      final limiter = SnackbarRateLimiter();
      expect(limiter.shouldShow(), isTrue);
      expect(limiter.shouldShow(), isFalse);
    });
  });

  group('parseInt', () {
    test('parses int directly', () {
      expect(parseInt(42), 42);
    });

    test('rounds double', () {
      expect(parseInt(42.7), 43);
      expect(parseInt(42.3), 42);
    });

    test('parses string', () {
      expect(parseInt('42'), 42);
    });

    test('returns null for non-numeric string', () {
      expect(parseInt('abc'), isNull);
    });

    test('returns null for null', () {
      expect(parseInt(null), isNull);
    });

    test('returns null for bool', () {
      expect(parseInt(true), isNull);
    });
  });
}
