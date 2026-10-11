import 'dart:io';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/http/read_retry.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';

class _Env extends Fake implements EnvFields {
  @override
  String get apiBaseUrl => 'https://example.test/';
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() => Env.init(_Env()));
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  void recoveryTest(String name, http.Response response, Duration expectedDelay, {double jitter = 0}) {
    test(name, () {
      fakeAsync((clock) {
        final now = DateTime.utc(2026, 10, 11);
        var attempts = 0;
        GetMemoriesResult? result;
        final reports = <GetMemoriesResult>[];
        getMemoriesResult(
          send: (url, headers) async {
            expect(Uri.parse(url).path, '/v3/memories');
            return ++attempts == 1 ? response : http.Response('[]', 200);
          },
          retry: ReadRetry(now: () => now.add(clock.elapsed), random: () => jitter),
          reportFailure: (failure) async => reports.add(failure),
        ).then((value) => result = value);
        clock.flushMicrotasks();
        expect(attempts, 1);
        expect(reports.single.statusCode, response.statusCode);
        expect(reports.single.failureReason, MemoriesFetchFailureReason.httpError);
        clock.elapse(expectedDelay - const Duration(microseconds: 1));
        expect(attempts, 1);
        clock.elapse(const Duration(microseconds: 1));
        expect(attempts, 2);
        expect(result!.ok, isTrue);
        expect(clock.pendingTimers, isEmpty);
      });
    });
  }

  recoveryTest('429 honors Retry-After seconds', http.Response('', 429, headers: {'retry-after': '4'}),
      const Duration(seconds: 4));
  recoveryTest(
      '503 honors Retry-After HTTP date',
      http.Response('', 503, headers: {'retry-after': HttpDate.format(DateTime.utc(2026, 10, 11, 0, 0, 5))}),
      const Duration(seconds: 5));
  recoveryTest(
      '503 uses exponential base with the lower jitter bound', http.Response('', 503), const Duration(seconds: 1));
  recoveryTest('503 uses exponential base with the upper jitter bound', http.Response('', 503),
      const Duration(milliseconds: 1249),
      jitter: 0.999999);
  recoveryTest('invalid Retry-After falls back to backoff', http.Response('', 429, headers: {'retry-after': 'invalid'}),
      const Duration(seconds: 1));
  recoveryTest('negative Retry-After falls back to backoff', http.Response('', 429, headers: {'retry-after': '-1'}),
      const Duration(seconds: 1));

  test('503 gives up after three attempts with 1s then 2s backoff and reports each failure once', () {
    fakeAsync((clock) {
      var attempts = 0;
      GetMemoriesResult? result;
      final reports = <GetMemoriesResult>[];
      getMemoriesResult(
        send: (_, __) async {
          attempts++;
          return http.Response('', 503);
        },
        retry: ReadRetry(random: () => 0),
        reportFailure: (failure) async => reports.add(failure),
      ).then((value) => result = value);
      clock.flushMicrotasks();
      expect(attempts, 1);
      clock.elapse(const Duration(seconds: 1));
      expect(attempts, 2);
      clock.elapse(const Duration(milliseconds: 1999));
      expect(attempts, 2);
      clock.elapse(const Duration(milliseconds: 1));
      expect(attempts, 3);
      expect(result!.ok, isFalse);
      expect(reports.map((failure) => failure.statusCode), [503, 503, 503]);
      expect(clock.pendingTimers, isEmpty);
    });
  });

  for (final status in [400, 401, 403, 404, 500, 502]) {
    test('$status does not automatically retry and remains a recoverable result', () async {
      var attempts = 0;
      final reports = <GetMemoriesResult>[];
      final result = await getMemoriesResult(
        send: (_, __) async {
          attempts++;
          return http.Response('', status);
        },
        reportFailure: (failure) async => reports.add(failure),
      );
      expect(attempts, 1);
      expect(result.ok, isFalse);
      expect(reports.single.statusCode, status);
    });
  }

  test('Retry-After beyond wait budget returns failure without retrying early', () async {
    var attempts = 0;
    final reports = <GetMemoriesResult>[];
    final result = await getMemoriesResult(
      send: (_, __) async {
        attempts++;
        return http.Response('', 429, headers: {'retry-after': '3600'});
      },
      retry: ReadRetry(wait: (_) async => fail('must not wait'), random: () => 0),
      reportFailure: (failure) async => reports.add(failure),
    );
    expect(attempts, 1);
    expect(result.statusCode, 429);
    expect(reports, hasLength(1));
  });

  test('legacy device-scope fallback keeps the retry policy and query', () async {
    final urls = <Uri>[];
    final statuses = [400, 503, 200].iterator;
    final reports = <GetMemoriesResult>[];
    final result = await getMemoriesResult(
      thisDeviceOnly: true,
      cursor: 'cursor-2',
      send: (url, _) async {
        urls.add(Uri.parse(url));
        statuses.moveNext();
        return http.Response('[]', statuses.current);
      },
      retry: ReadRetry(wait: (_) async {}, random: () => 0),
      reportFailure: (failure) async => reports.add(failure),
    );
    expect(result.ok, isTrue);
    expect(result.deviceScopeSupported, isFalse);
    expect(urls.first.queryParameters['device_scope'], 'current');
    expect(urls.skip(1).every((url) => !url.queryParameters.containsKey('device_scope')), isTrue);
    expect(urls.every((url) => url.queryParameters['cursor'] == 'cursor-2'), isTrue);
    expect(reports.single.statusCode, 503);
  });

  test('unexpected send errors propagate to the existing uncaught-error policy', () async {
    final error = StateError('programming defect');
    await expectLater(
      getMemoriesResult(send: (_, __) async => throw error),
      throwsA(same(error)),
    );
  });
}
