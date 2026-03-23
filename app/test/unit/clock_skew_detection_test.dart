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
  });

  group('ClockSkewEvent.skewMinutes', () {
    test('converts seconds to minutes (ceiling)', () {
      expect(ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 900, hint: null).skewMinutes, 15);
      expect(ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 300, hint: null).skewMinutes, 5);
      expect(ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 301, hint: null).skewMinutes, 6);
    });

    test('minimum 1 minute', () {
      expect(ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 0, hint: null).skewMinutes, 1);
      expect(ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 1, hint: null).skewMinutes, 1);
      expect(ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: 59, hint: null).skewMinutes, 1);
    });

    test('handles negative skew (abs value)', () {
      expect(ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: -900, hint: null).skewMinutes, 15);
      expect(ClockSkewEvent(serverTime: null, clientTime: null, skewSeconds: -1, hint: null).skewMinutes, 1);
    });
  });

  group('ClockSkewDetector.checkResponse', () {
    late ClockSkewDetector detector;

    setUp(() {
      detector = ClockSkewDetector.instance;
      detector.resetForTesting();
    });

    http.Response _makeValid408() {
      return _make408(
        body: jsonEncode({'error': 'clock_skew', 'skew_seconds': 900}),
      );
    }

    test('emits event on first valid 408', () async {
      final events = <ClockSkewEvent>[];
      final sub = detector.onClockSkew.listen(events.add);

      detector.checkResponse(_makeValid408());
      await Future.delayed(Duration.zero);

      expect(events, hasLength(1));
      expect(events.first.skewSeconds, 900);
      await sub.cancel();
    });

    test('suppresses second event within cooldown', () async {
      final events = <ClockSkewEvent>[];
      final sub = detector.onClockSkew.listen(events.add);

      detector.checkResponse(_makeValid408());
      detector.checkResponse(_makeValid408());
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
  });
}
