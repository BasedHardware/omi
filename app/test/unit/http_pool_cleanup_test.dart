import 'dart:async';
import 'dart:io';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/http_pool_manager.dart';

void main() {
  final client = _ScriptedClient();
  late HttpPoolManager manager;
  final url = Uri.parse('https://http-cleanup.invalid/test');

  setUpAll(() {
    manager = HttpOverrides.runZoned(() => HttpPoolManager.instance, createHttpClient: (_) => client);
  });
  setUp(() => client.attempts = 0);
  tearDownAll(() => manager.dispose());

  for (final error in <Object>[
    const SocketException('Connection refused'),
    const HandshakeException('TLS handshake failed'),
    TimeoutException('Request timeout'),
    StateError('Unexpected request failure'),
  ]) {
    test('GET ${error.runtimeType} reaches the caller without an uncaught cleanup error', () {
      fakeAsync((async) {
        client.reply = () => Future.error(error);
        final caught = <Object>[];
        final uncaught = <Object>[];
        runZonedGuarded(() {
          manager
              .send(() => http.Request('GET', url), retries: 0)
              .then<void>((_) => fail('Request unexpectedly succeeded'), onError: (Object e) => caught.add(e));
        }, (error, _) => uncaught.add(error));

        async.flushMicrotasks();

        expect(client.attempts, 1);
        expect(caught, hasLength(1));
        // IOClient wraps SocketException but preserves its socket semantics.
        if (error is SocketException) {
          expect(caught.single, isA<SocketException>());
        } else if (error is TimeoutException) {
          expect(caught.single, isA<TimeoutException>());
        } else {
          expect(caught.single, same(error));
        }
        expect(uncaught, isEmpty);
      });
    });
  }

  test('concurrent failed GETs share one request and a later GET tries again', () {
    fakeAsync((async) {
      late Completer<HttpClientRequest> pending;
      final caught = <Object>[];
      final uncaught = <Object>[];
      void send() {
        manager
            .send(() => http.Request('GET', url), retries: 0)
            .then<void>((_) => fail('Request unexpectedly succeeded'), onError: (Object e) => caught.add(e));
      }

      runZonedGuarded(() {
        pending = Completer<HttpClientRequest>();
        client.reply = () => pending.future;
        send();
        send();
        async.flushMicrotasks();
        expect(client.attempts, 1);
        pending.completeError(const SocketException('Connection refused'));
        async.flushMicrotasks();
        expect(caught, hasLength(2));
        expect(caught.first, same(caught.last));

        send();
        async.flushMicrotasks();
      }, (error, _) => uncaught.add(error));

      expect(client.attempts, 2);
      expect(caught, hasLength(3));
      expect(uncaught, isEmpty);
    });
  });

  test('successful GETs deduplicate only while pending and complete after cleanup', () {
    fakeAsync((async) {
      final pending = Completer<HttpClientRequest>();
      client.reply = () => pending.future;
      final responses = <http.Response>[];
      void send() => manager.send(() => http.Request('GET', url), retries: 0).then(responses.add);

      send();
      send();
      async.flushMicrotasks();
      expect(client.attempts, 1);
      pending.complete(_SuccessfulRequest());
      async.flushMicrotasks();
      expect(responses, hasLength(2));
      expect(responses.first.statusCode, HttpStatus.ok);
      expect(responses.first, same(responses.last));

      client.reply = () async => _SuccessfulRequest();
      send();
      async.flushMicrotasks();
      expect(client.attempts, 2);
      expect(responses, hasLength(3));
    });
  });

  test('exhausted GET retries propagate one error without an uncaught cleanup error', () {
    fakeAsync((async) {
      client.reply = () => Future.error(const SocketException('Connection refused'));
      final caught = <Object>[];
      final uncaught = <Object>[];
      runZonedGuarded(() {
        manager
            .send(() => http.Request('GET', url))
            .then<void>((_) => fail('Request unexpectedly succeeded'), onError: (Object e) => caught.add(e));
      }, (error, _) => uncaught.add(error));

      async.flushMicrotasks();
      expect(client.attempts, 1);
      expect(caught, isEmpty);
      async.elapse(const Duration(milliseconds: 200));
      expect(client.attempts, 2);
      expect(caught, hasLength(1));
      expect(uncaught, isEmpty);
    });
  });
}

class _ScriptedClient extends Fake implements HttpClient {
  late Future<HttpClientRequest> Function() reply;
  int attempts = 0;

  @override
  int? maxConnectionsPerHost;
  @override
  Duration idleTimeout = Duration.zero;

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) {
    attempts++;
    return reply();
  }

  @override
  void close({bool force = false}) {}
}

class _SuccessfulRequest extends Fake implements HttpClientRequest {
  @override
  final HttpHeaders headers = _EmptyHeaders();
  @override
  bool followRedirects = true;
  @override
  int maxRedirects = 5;
  @override
  bool persistentConnection = true;
  @override
  int contentLength = 0;

  @override
  Future<void> addStream(Stream<List<int>> stream) => stream.drain<void>();
  @override
  Future<HttpClientResponse> close() async => _SuccessfulResponse();
}

class _SuccessfulResponse extends Stream<List<int>> implements HttpClientResponse {
  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int>)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) =>
      const Stream<List<int>>.empty().listen(onData, onError: onError, onDone: onDone, cancelOnError: cancelOnError);

  @override
  HttpHeaders get headers => _EmptyHeaders();
  @override
  int get statusCode => HttpStatus.ok;
  @override
  int get contentLength => 0;
  @override
  bool get isRedirect => false;
  @override
  List<RedirectInfo> get redirects => const [];
  @override
  bool get persistentConnection => true;
  @override
  String get reasonPhrase => 'OK';
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _EmptyHeaders extends Fake implements HttpHeaders {
  @override
  void set(String name, Object value, {bool preserveHeaderCase = false}) {}
  @override
  void forEach(void Function(String, List<String>) action) {}
}
