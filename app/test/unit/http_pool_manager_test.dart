import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/http_pool_manager.dart';

class _FakeHttpOverrides extends HttpOverrides {
  _FakeHttpOverrides(this.client);

  final _FakeHttpClient client;

  @override
  HttpClient createHttpClient(SecurityContext? context) => client;
}

class _FakeHttpClient implements HttpClient {
  final List<Completer<HttpClientRequest>> opens = [];

  int get openCount => opens.length;

  void reset() => opens.clear();

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) {
    final completer = Completer<HttpClientRequest>();
    opens.add(completer);
    return completer.future;
  }

  @override
  int? maxConnectionsPerHost = 15;

  @override
  Duration idleTimeout = const Duration(seconds: 15);

  @override
  void close({bool force = false}) {}

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('fake client does not implement ${invocation.memberName}');
}

class _FakeRequest implements HttpClientRequest {
  _FakeRequest(this._response);

  final HttpClientResponse _response;

  @override
  HttpHeaders get headers => _FakeHttpHeaders();

  @override
  bool followRedirects = false;

  @override
  int maxRedirects = 5;

  @override
  bool persistentConnection = true;

  @override
  int contentLength = -1;

  @override
  Future<void> addStream(Stream<List<int>> stream) => stream.drain<void>();

  @override
  Future<HttpClientResponse> close() async => _response;

  @override
  Future<HttpClientResponse> get done => close();

  @override
  void abort([Object? error, StackTrace? stackTrace]) {}

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('fake request does not implement ${invocation.memberName}');
}

class _FakeResponse extends Stream<List<int>> implements HttpClientResponse {
  _FakeResponse(this.statusCode, this.body);

  @override
  final int statusCode;

  final String body;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int> data)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream<List<int>>.fromIterable([
      utf8.encode(body),
    ]).listen(onData, onError: onError, onDone: onDone, cancelOnError: cancelOnError);
  }

  @override
  HttpHeaders get headers => _FakeHttpHeaders();

  @override
  String get reasonPhrase => '';

  @override
  bool get isRedirect => false;

  @override
  List<RedirectInfo> get redirects => const [];

  @override
  bool get persistentConnection => true;

  @override
  int get contentLength => utf8.encode(body).length;

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('fake response does not implement ${invocation.memberName}');
}

class _FakeHungBodyResponse extends _FakeResponse {
  _FakeHungBodyResponse(super.statusCode, super.body);

  late final StreamController<List<int>> bodyStream = StreamController<List<int>>(
    onCancel: () => cancelObserved = true,
  );

  bool cancelObserved = false;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int> data)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return bodyStream.stream.listen(onData, onError: onError, onDone: onDone, cancelOnError: cancelOnError);
  }
}

class _FakeHttpHeaders implements HttpHeaders {
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// Headers arrive, the body never does: a server that accepts the request and
/// then stalls the response body.
class _StalledBodyResponse extends Stream<List<int>> implements HttpClientResponse {
  _StalledBodyResponse(this.statusCode);

  @override
  final int statusCode;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int> data)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    // A stream that never emits data, done, or error: `fromStream` blocks on
    // the body until the deadline covers it.
    final controller = StreamController<List<int>>();
    return controller.stream.listen(onData, onError: onError, onDone: onDone, cancelOnError: cancelOnError);
  }

  @override
  HttpHeaders get headers => _FakeHttpHeaders();

  @override
  String get reasonPhrase => '';

  @override
  bool get isRedirect => false;

  @override
  List<RedirectInfo> get redirects => const [];

  @override
  bool get persistentConnection => true;

  @override
  int get contentLength => -1;

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError('stalled fake response');
}

void main() {
  late _FakeHttpClient client;

  setUpAll(() {
    client = _FakeHttpClient();
    HttpOverrides.runWithHttpOverrides(() => HttpPoolManager.instance, _FakeHttpOverrides(client));
  });

  tearDownAll(() {
    HttpPoolManager.instance.dispose();
  });

  setUp(() => client.reset());

  Future<Completer<HttpClientRequest>> waitForOpen(int index) async {
    for (var i = 0; i < 200; i++) {
      if (client.opens.length > index) return client.opens[index];
      await Future<void>.delayed(const Duration(milliseconds: 1));
    }
    throw StateError('no openUrl call reached the fake client (index $index)');
  }

  Future<void> flushEventQueue() async {
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
  }

  Future<({List<Object> unhandled, Object? harnessError})> runInGuardedZone(Future<void> Function() body) async {
    final unhandled = <Object>[];
    final done = Completer<void>();
    Object? harnessError;
    runZonedGuarded(() async {
      try {
        await body();
      } catch (e) {
        harnessError = e;
      } finally {
        await flushEventQueue();
        done.complete();
      }
    }, (error, stackTrace) => unhandled.add(error));
    await done.future;
    return (unhandled: unhandled, harnessError: harnessError);
  }

  group('HttpPoolManager GET deduplication', () {
    test('a failing GET delivers the error to its caller and raises no unhandled zone error', () async {
      final url = Uri.parse('http://pool-http-fake.invalid/get-fails');
      http.Response? callerResponse;
      Object? callerError;

      final outcome = await runInGuardedZone(() async {
        final send = HttpPoolManager.instance.send(() => http.Request('GET', url), retries: 0);
        final observed = () async {
          try {
            callerResponse = await send;
          } catch (e) {
            callerError = e;
          }
        }();
        (await waitForOpen(0)).completeError(const SocketException('pool-dedup-boom'));
        await observed;
      });

      expect(outcome.harnessError, isNull);
      expect(callerResponse, isNull);
      expect(callerError, allOf(isA<http.ClientException>(), isA<SocketException>()));
      expect((callerError as http.ClientException).message, contains('pool-dedup-boom'));
      expect(client.openCount, 1);
      expect(outcome.unhandled, isEmpty);
    });

    test('two concurrent identical failing GETs share one request and both callers get the same error', () async {
      final url = Uri.parse('http://pool-http-fake.invalid/get-fails-concurrent');
      http.Response? firstResponse, secondResponse;
      Object? firstError, secondError;

      final outcome = await runInGuardedZone(() async {
        final first = HttpPoolManager.instance.send(() => http.Request('GET', url), retries: 0);
        final second = HttpPoolManager.instance.send(() => http.Request('GET', url), retries: 0);
        final observedFirst = () async {
          try {
            firstResponse = await first;
          } catch (e) {
            firstError = e;
          }
        }();
        final observedSecond = () async {
          try {
            secondResponse = await second;
          } catch (e) {
            secondError = e;
          }
        }();
        (await waitForOpen(0)).completeError(const SocketException('pool-dedup-boom'));
        await Future.wait([observedFirst, observedSecond]);
      });

      expect(outcome.harnessError, isNull);
      expect(firstResponse, isNull);
      expect(secondResponse, isNull);
      expect(firstError, allOf(isA<http.ClientException>(), isA<SocketException>()));
      expect(secondError, allOf(isA<http.ClientException>(), isA<SocketException>()));
      expect(identical(firstError, secondError), isTrue);
      expect(client.openCount, 1);
      expect(outcome.unhandled, isEmpty);
    });

    test('concurrent successful GETs share one response and a later identical GET issues a new request', () async {
      final url = Uri.parse('http://pool-http-fake.invalid/get-succeeds');
      http.Response? firstResponse, secondResponse, laterResponse;
      Object? firstError, secondError, laterError;

      final outcome = await runInGuardedZone(() async {
        final first = HttpPoolManager.instance.send(() => http.Request('GET', url), retries: 0);
        final second = HttpPoolManager.instance.send(() => http.Request('GET', url), retries: 0);
        final observedFirst = () async {
          try {
            firstResponse = await first;
          } catch (e) {
            firstError = e;
          }
        }();
        final observedSecond = () async {
          try {
            secondResponse = await second;
          } catch (e) {
            secondError = e;
          }
        }();
        (await waitForOpen(0)).complete(_FakeRequest(_FakeResponse(200, 'first-body')));
        await Future.wait([observedFirst, observedSecond]);
        await flushEventQueue();

        final later = HttpPoolManager.instance.send(() => http.Request('GET', url), retries: 0);
        final observedLater = () async {
          try {
            laterResponse = await later;
          } catch (e) {
            laterError = e;
          }
        }();
        (await waitForOpen(1)).complete(_FakeRequest(_FakeResponse(200, 'later-body')));
        await observedLater;
      });

      expect(outcome.harnessError, isNull);
      expect(firstError, isNull);
      expect(secondError, isNull);
      expect(laterError, isNull);
      expect(firstResponse?.statusCode, 200);
      expect(firstResponse?.body, 'first-body');
      expect(identical(firstResponse, secondResponse), isTrue);
      expect(laterResponse?.statusCode, 200);
      expect(laterResponse?.body, 'later-body');
      expect(client.openCount, 2);
      expect(outcome.unhandled, isEmpty);
    });

    test('a failed GET is not retained: a later identical GET issues a new request that can succeed', () async {
      final url = Uri.parse('http://pool-http-fake.invalid/get-fails-then-succeeds');
      http.Response? firstResponse, laterResponse;
      Object? firstError, laterError;

      final outcome = await runInGuardedZone(() async {
        final first = HttpPoolManager.instance.send(() => http.Request('GET', url), retries: 0);
        final observedFirst = () async {
          try {
            firstResponse = await first;
          } catch (e) {
            firstError = e;
          }
        }();
        (await waitForOpen(0)).completeError(const SocketException('pool-dedup-boom'));
        await observedFirst;
        await flushEventQueue();

        final later = HttpPoolManager.instance.send(() => http.Request('GET', url), retries: 0);
        final observedLater = () async {
          try {
            laterResponse = await later;
          } catch (e) {
            laterError = e;
          }
        }();
        (await waitForOpen(1)).complete(_FakeRequest(_FakeResponse(200, 'recovered')));
        await observedLater;
      });

      expect(outcome.harnessError, isNull);
      expect(firstResponse, isNull);
      expect(firstError, allOf(isA<http.ClientException>(), isA<SocketException>()));
      expect(laterError, isNull);
      expect(laterResponse?.statusCode, 200);
      expect(laterResponse?.body, 'recovered');
      expect(client.openCount, 2);
      expect(outcome.unhandled, isEmpty);
    });
    test('a stalled response body settles at the deadline instead of hanging', () async {
      final url = Uri.parse('http://pool-http-fake.invalid/body-stalls');
      http.Response? callerResponse;
      Object? callerError;

      // Headers arrive; the body never does.
      final response = _StalledBodyResponse(200);
      final outcome = await runInGuardedZone(() async {
        final send = HttpPoolManager.instance.send(
          () => http.Request('GET', url),
          timeout: const Duration(milliseconds: 50),
          retries: 0,
        );
        final observed = () async {
          try {
            callerResponse = await send;
          } catch (e) {
            callerError = e;
          }
        }();
        (await waitForOpen(0)).complete(_FakeRequest(response));
        await Future<void>.delayed(const Duration(milliseconds: 250));
        await observed;
      });

      expect(outcome.harnessError, isNull);
      expect(callerResponse, isNull, reason: 'a stalled body must not produce a response');
      expect(callerError, isA<TimeoutException>(), reason: 'the deadline covers body consumption');
      expect(outcome.unhandled, isEmpty);
    });

    test('a response whose body never closes times out, aborts the stream, and frees the GET dedup slot', () async {
      final url = Uri.parse('http://pool-http-fake.invalid/get-hung-body');
      final hung = _FakeHungBodyResponse(200, '');
      http.Response? laterResponse;
      Object? firstError, laterError;

      final outcome = await runInGuardedZone(() async {
        final first = HttpPoolManager.instance
            .send(() => http.Request('GET', url), timeout: const Duration(milliseconds: 50), retries: 0);
        final observedFirst = () async {
          try {
            await first;
          } catch (e) {
            firstError = e;
          }
        }();
        (await waitForOpen(0)).complete(_FakeRequest(hung));
        await observedFirst;
        await flushEventQueue();

        final later = HttpPoolManager.instance.send(() => http.Request('GET', url), retries: 0);
        final observedLater = () async {
          try {
            laterResponse = await later;
          } catch (e) {
            laterError = e;
          }
        }();
        (await waitForOpen(1)).complete(_FakeRequest(_FakeResponse(200, 'recovered')));
        await observedLater;
      });

      expect(outcome.harnessError, isNull);
      expect(firstError, isA<TimeoutException>());
      expect(hung.cancelObserved, isTrue);
      expect(laterError, isNull);
      expect(laterResponse?.body, 'recovered');
      expect(client.openCount, 2);
      expect(outcome.unhandled, isEmpty);
    });
  });
}
