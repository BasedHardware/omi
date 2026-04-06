import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/http_pool_manager.dart';

/// Tests that HttpPoolManager.stampRequestTime() refreshes
/// X-Request-Start-Time on each call, ensuring retries, pool-queued
/// requests, and multipart uploads don't send stale timestamps.
///
/// stampRequestTime is the single enforcement point: every HTTP request
/// to the Omi backend flows through send() or sendStreaming(), both of
/// which call it right before _client.send(). (#6274)
///
/// The "wiring" group verifies that send() and sendStreaming() actually
/// call stampRequestTime before transmitting, using a local HTTP server.

void main() {
  group('HttpPoolManager.stampRequestTime', () {
    test('stamps a fresh X-Request-Start-Time on a request', () {
      final request = http.Request('GET', Uri.parse('https://api.example.com/v1/test'));
      request.headers['X-Request-Start-Time'] = '1000000000.0'; // stale (year 2001)

      HttpPoolManager.stampRequestTime(request);

      final ts = double.parse(request.headers['X-Request-Start-Time']!);
      expect(ts, greaterThan(1700000000.0));
    });

    test('each call produces a fresh timestamp', () async {
      final request1 = http.Request('GET', Uri.parse('https://api.example.com/v1/test'));
      HttpPoolManager.stampRequestTime(request1);
      final ts1 = double.parse(request1.headers['X-Request-Start-Time']!);

      await Future.delayed(const Duration(milliseconds: 10));

      final request2 = http.Request('GET', Uri.parse('https://api.example.com/v1/test'));
      HttpPoolManager.stampRequestTime(request2);
      final ts2 = double.parse(request2.headers['X-Request-Start-Time']!);

      expect(ts1, greaterThan(1700000000.0));
      expect(ts2, greaterThan(1700000000.0));
      expect(ts2, greaterThanOrEqualTo(ts1));
    });

    test('works on MultipartRequest (upload path)', () {
      final request = http.MultipartRequest('POST', Uri.parse('https://api.example.com/v1/upload'));
      request.headers['X-Request-Start-Time'] = '1000000000.0';

      HttpPoolManager.stampRequestTime(request);

      final ts = double.parse(request.headers['X-Request-Start-Time']!);
      expect(ts, greaterThan(1700000000.0));
    });

    test('simulated retry loop gets fresh timestamps', () async {
      final timestamps = <double>[];

      for (var i = 0; i <= 2; i++) {
        final request = http.Request('PATCH', Uri.parse('https://api.example.com/v1/test'));
        HttpPoolManager.stampRequestTime(request);
        timestamps.add(double.parse(request.headers['X-Request-Start-Time']!));
        if (i < 2) {
          await Future.delayed(const Duration(milliseconds: 10));
        }
      }

      for (final ts in timestamps) {
        expect(ts, greaterThan(1700000000.0));
      }

      for (var i = 1; i < timestamps.length; i++) {
        expect(timestamps[i], greaterThanOrEqualTo(timestamps[i - 1]));
      }
    });
  });

  group('HttpPoolManager send/sendStreaming wiring', () {
    late HttpServer server;
    late String baseUrl;

    setUp(() async {
      server = await HttpServer.bind('127.0.0.1', 0);
      baseUrl = 'http://127.0.0.1:${server.port}';
    });

    tearDown(() async {
      await server.close(force: true);
    });

    test('send() overwrites stale timestamp before transmitting', () async {
      String? receivedTimestamp;

      server.listen((request) {
        receivedTimestamp = request.headers.value('x-request-start-time');
        request.response
          ..statusCode = 200
          ..write('ok')
          ..close();
      });

      final response = await HttpPoolManager.instance.send(() {
        final req = http.Request('POST', Uri.parse('$baseUrl/test'));
        req.headers['X-Request-Start-Time'] = '1000000000.0';
        return req;
      }, retries: 0);

      expect(response.statusCode, 200);
      expect(receivedTimestamp, isNotNull);
      final ts = double.parse(receivedTimestamp!);
      expect(ts, greaterThan(1700000000.0));
    });

    test('sendStreaming() overwrites stale timestamp before transmitting', () async {
      String? receivedTimestamp;

      server.listen((request) {
        receivedTimestamp = request.headers.value('x-request-start-time');
        request.response
          ..statusCode = 200
          ..write('ok')
          ..close();
      });

      final request = http.Request('POST', Uri.parse('$baseUrl/test'));
      request.headers['X-Request-Start-Time'] = '1000000000.0';

      final streamedResponse = await HttpPoolManager.instance.sendStreaming(request);
      // Drain the response to complete the request
      await streamedResponse.stream.drain<void>();

      expect(streamedResponse.statusCode, 200);
      expect(receivedTimestamp, isNotNull);
      final ts = double.parse(receivedTimestamp!);
      expect(ts, greaterThan(1700000000.0));
    });
  });
}
