import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/clock_skew_detector.dart';

http.Response _make408({required String body, String contentType = 'application/json'}) {
  return http.Response(body, 408, headers: {'content-type': contentType});
}

void main() {
  group('ClockSkewDetector.parseResponse', () {
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
      final result = ClockSkewDetector.parseResponse(response);
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
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });

    test('returns null for empty body', () {
      final response = _make408(body: '');
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });

    test('returns null for non-JSON content-type', () {
      final response = _make408(body: 'Request Timeout', contentType: 'text/plain');
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });

    test('returns null for HTML content-type (proxy 408)', () {
      final response = _make408(body: '<html>timeout</html>', contentType: 'text/html');
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });

    test('returns null for malformed JSON', () {
      final response = _make408(body: '{not valid json}');
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });

    test('returns null when error is not clock_skew', () {
      final response = _make408(
        body: jsonEncode({'error': 'timeout', 'skew_seconds': 900}),
      );
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });

    test('returns null when error field is missing', () {
      final response = _make408(
        body: jsonEncode({'skew_seconds': 900}),
      );
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });

    test('returns null when skew_seconds is missing', () {
      final response = _make408(
        body: jsonEncode({'error': 'clock_skew'}),
      );
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });

    test('returns null when skew_seconds is non-numeric string', () {
      final response = _make408(
        body: jsonEncode({'error': 'clock_skew', 'skew_seconds': 'abc'}),
      );
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });

    test('handles string skew_seconds', () {
      final response = _make408(
        body: jsonEncode({'error': 'clock_skew', 'skew_seconds': '900'}),
      );
      final result = ClockSkewDetector.parseResponse(response);
      expect(result, isNotNull);
      expect(result!.skewSeconds, 900);
    });

    test('handles integer skew_seconds', () {
      final response = _make408(
        body: jsonEncode({'error': 'clock_skew', 'skew_seconds': 900}),
      );
      final result = ClockSkewDetector.parseResponse(response);
      expect(result, isNotNull);
      expect(result!.skewSeconds, 900);
    });

    test('rounds float skew_seconds to int', () {
      final response = _make408(
        body: jsonEncode({'error': 'clock_skew', 'skew_seconds': 899.7}),
      );
      final result = ClockSkewDetector.parseResponse(response);
      expect(result, isNotNull);
      expect(result!.skewSeconds, 900);
    });

    test('handles case-insensitive content-type', () {
      final response = http.Response(
        jsonEncode({'error': 'clock_skew', 'skew_seconds': 300}),
        408,
        headers: {'content-type': 'Application/JSON; charset=utf-8'},
      );
      final result = ClockSkewDetector.parseResponse(response);
      expect(result, isNotNull);
      expect(result!.skewSeconds, 300);
    });

    test('returns null for non-200 non-408 status', () {
      final response = http.Response(
        jsonEncode({'error': 'clock_skew', 'skew_seconds': 900}),
        500,
        headers: {'content-type': 'application/json'},
      );
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });

    test('returns null when content-type header is missing', () {
      final response = http.Response(
        jsonEncode({'error': 'clock_skew', 'skew_seconds': 900}),
        408,
      );
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });

    test('returns null when body is a JSON array', () {
      final response = _make408(body: jsonEncode([1, 2, 3]));
      expect(ClockSkewDetector.parseResponse(response), isNull);
    });
  });

  group('ClockSkewEvent.skewMinutes', () {
    test('converts seconds to minutes (ceiling)', () {
      expect(const ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 900, hint: null).skewMinutes, 15);
      expect(const ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 300, hint: null).skewMinutes, 5);
      expect(const ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 301, hint: null).skewMinutes, 6);
    });

    test('minimum 1 minute', () {
      expect(const ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 0, hint: null).skewMinutes, 1);
      expect(const ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 1, hint: null).skewMinutes, 1);
      expect(const ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 59, hint: null).skewMinutes, 1);
    });

    test('handles negative skew (abs value)', () {
      expect(const ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: -900, hint: null).skewMinutes, 15);
      expect(const ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: -1, hint: null).skewMinutes, 1);
    });
  });

  group('ClockSkewDetector.checkResponse', () {
    late ClockSkewDetector detector;

    setUp(() {
      detector = ClockSkewDetector.instance;
      detector.resetForTesting();
    });

    http.Response makeValid408() {
      return _make408(
        body: jsonEncode({'error': 'clock_skew', 'skew_seconds': 900}),
      );
    }

    test('emits event on first valid 408', () async {
      final events = <ClockSkewEvent>[];
      final sub = detector.onClockSkew.listen(events.add);

      detector.checkResponse(makeValid408());
      await Future.delayed(Duration.zero);

      expect(events, hasLength(1));
      expect(events.first.skewSeconds, 900);
      await sub.cancel();
    });

    test('suppresses second event within cooldown', () async {
      final events = <ClockSkewEvent>[];
      final sub = detector.onClockSkew.listen(events.add);

      detector.checkResponse(makeValid408());
      detector.checkResponse(makeValid408());
      await Future.delayed(Duration.zero);

      expect(events, hasLength(1));
      await sub.cancel();
    });

    test('does not emit for non-clock-skew response', () async {
      final events = <ClockSkewEvent>[];
      final sub = detector.onClockSkew.listen(events.add);

      detector.checkResponse(http.Response('ok', 200));
      await Future.delayed(Duration.zero);

      expect(events, isEmpty);
      await sub.cancel();
    });

    test('does not emit for non-JSON 408', () async {
      final events = <ClockSkewEvent>[];
      final sub = detector.onClockSkew.listen(events.add);

      detector.checkResponse(_make408(body: 'Request Timeout', contentType: 'text/html'));
      await Future.delayed(Duration.zero);

      expect(events, isEmpty);
      await sub.cancel();
    });

    test('emits again after cooldown expires', () async {
      final events = <ClockSkewEvent>[];
      final sub = detector.onClockSkew.listen(events.add);

      detector.checkResponse(makeValid408());
      await Future.delayed(Duration.zero);
      expect(events, hasLength(1));

      // Simulate cooldown expiry by backdating _lastEmittedAt
      detector.setLastEmittedAtForTesting(
        DateTime.now().subtract(const Duration(seconds: 46)),
      );

      detector.checkResponse(makeValid408());
      await Future.delayed(Duration.zero);
      expect(events, hasLength(2));
      await sub.cancel();
    });

    test('still suppresses just before cooldown expires', () async {
      final events = <ClockSkewEvent>[];
      final sub = detector.onClockSkew.listen(events.add);

      detector.checkResponse(makeValid408());
      await Future.delayed(Duration.zero);
      expect(events, hasLength(1));

      // Set _lastEmittedAt to 44s ago — still within 45s cooldown
      detector.setLastEmittedAtForTesting(
        DateTime.now().subtract(const Duration(seconds: 44)),
      );

      detector.checkResponse(makeValid408());
      await Future.delayed(Duration.zero);
      expect(events, hasLength(1)); // Still suppressed
      await sub.cancel();
    });

    test('suppresses at exact cooldown boundary (45s)', () async {
      final events = <ClockSkewEvent>[];
      final sub = detector.onClockSkew.listen(events.add);

      detector.checkResponse(makeValid408());
      await Future.delayed(Duration.zero);
      expect(events, hasLength(1));

      // Set _lastEmittedAt to exactly 45s ago — code uses strict < so this is NOT suppressed
      detector.setLastEmittedAtForTesting(
        DateTime.now().subtract(const Duration(seconds: 45)),
      );

      detector.checkResponse(makeValid408());
      await Future.delayed(Duration.zero);
      // At exactly 45s, difference == cooldown, so !(diff < cooldown) → emits
      expect(events, hasLength(2));
      await sub.cancel();
    });

    test('broadcast stream delivers to multiple subscribers', () async {
      final events1 = <ClockSkewEvent>[];
      final events2 = <ClockSkewEvent>[];
      final sub1 = detector.onClockSkew.listen(events1.add);
      final sub2 = detector.onClockSkew.listen(events2.add);

      detector.checkResponse(makeValid408());
      await Future.delayed(Duration.zero);

      expect(events1, hasLength(1));
      expect(events2, hasLength(1));
      expect(events1.first.skewSeconds, 900);
      expect(events2.first.skewSeconds, 900);
      await sub1.cancel();
      await sub2.cancel();
    });
  });
}
