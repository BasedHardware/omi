import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/http_pool_manager.dart';

/// Pooled keep-alive sockets outlive a Wi-Fi/cellular switch: uploads a few
/// seconds apart never let one idle out, and iOS then fails the reused socket
/// with EADDRNOTAVAIL ("Can't assign requested address"). These run the real
/// dart:io pool against loopback servers and record which client socket
/// carried each request.
void main() {
  late HttpServer server;
  late Uri baseUri;
  late List<int> sourcePorts;
  late List<HttpRequest> stalled;
  late bool dropNextConnection;
  late HttpPoolManager manager;

  setUp(() async {
    sourcePorts = [];
    stalled = [];
    dropNextConnection = false;
    manager = HttpPoolManager.forTesting();
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    baseUri = Uri.parse('http://127.0.0.1:${server.port}');
    server.listen((request) async {
      sourcePorts.add(request.connectionInfo!.remotePort);
      await request.drain<void>();
      if (request.uri.path == '/stall') {
        // Never answered: the request waits for headers until someone closes it.
        stalled.add(request);
        return;
      }
      if (request.uri.path == '/redirect') {
        await request.response.redirect(baseUri.resolve('/stream'), status: HttpStatus.seeOther);
        return;
      }
      if (request.uri.path == '/body-waits') {
        request.response.contentLength = 5;
        request.response.add([1]);
        await request.response.flush();
        return;
      }
      if (request.uri.path == '/stream') {
        request.response.statusCode = HttpStatus.ok;
        request.response.contentLength = 5;
        request.response.headers.set('x-network-test', 'kept');
        for (var i = 0; i < 5; i++) {
          request.response.add([i]);
          await request.response.flush();
          await Future<void>.delayed(const Duration(milliseconds: 80));
        }
        await request.response.close();
        return;
      }
      if (request.uri.path == '/slow-headers') {
        await Future<void>.delayed(const Duration(milliseconds: 400));
      }
      if (request.uri.path == '/drop-body') {
        request.response.contentLength = 5;
        request.response.add([1]);
        await request.response.flush();
        request.response.deadline = const Duration(milliseconds: 50);
        return;
      }
      if (dropNextConnection) {
        dropNextConnection = false;
        // The connection dies while the client waits for the response.
        final socket = await request.response.detachSocket(writeHeaders: false);
        socket.destroy();
        return;
      }
      request.response.statusCode = HttpStatus.accepted;
      await request.response.close();
    });
  });

  tearDown(() async {
    manager.dispose();
    await server.close(force: true);
  });

  Future<http.StreamedResponse> start(String path, {HttpPoolManager? on}) =>
      (on ?? manager).sendStreaming(http.Request('POST', baseUri.resolve(path))..body = 'audio');

  Future<int> upload({HttpPoolManager? on}) async {
    final response = await start('/v2/sync-local-files', on: on);
    await response.stream.drain<void>();
    return response.statusCode;
  }

  /// Two concurrent uploads leave two idle keep-alive sockets in the pool.
  Future<Set<int>> fillPool() async {
    await Future.wait([upload(), upload()]);
    final pooled = sourcePorts.toSet();
    expect(pooled, hasLength(2));
    return pooled;
  }

  /// The error a request ended with, or 'still open' if it outlived [within].
  Future<Object?> outcome(Future<http.StreamedResponse> request, {Duration within = const Duration(seconds: 5)}) =>
      request.then<Object?>((_) => 'answered', onError: (Object error) => error).timeout(
            within,
            onTimeout: () => 'still open',
          );

  Future<void> untilStalled(int count) async {
    while (stalled.length < count) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
    }
  }

  test('consecutive uploads ride one pooled socket', () async {
    expect(await upload(), HttpStatus.accepted);
    expect(await upload(), HttpStatus.accepted);

    expect(sourcePorts[1], sourcePorts[0]);
  });

  test('after a network switch the next upload opens a new socket', () async {
    await upload();
    manager.resetConnections();
    expect(await upload(), HttpStatus.accepted);

    expect(sourcePorts[1], isNot(sourcePorts[0]));
  });

  test('a dropped upload connection retires its idle siblings', () async {
    final pooled = await fillPool();
    dropNextConnection = true;

    await expectLater(upload(), throwsA(isA<http.ClientException>()));
    expect(pooled, contains(sourcePorts.last), reason: 'the failed upload reused a pooled socket');

    expect(await upload(), HttpStatus.accepted);
    expect(pooled, isNot(contains(sourcePorts.last)), reason: 'the next upload must not reuse a sibling socket');
  });

  test('a pooled request retries a dropped connection on a new socket', () async {
    final pooled = await fillPool();
    dropNextConnection = true;

    final response = await manager.send(
      () => http.Request('POST', baseUri.resolve('/v2/sync-local-files'))..body = 'audio',
      retries: 1,
    );

    expect(response.statusCode, HttpStatus.accepted);
    expect(pooled, contains(sourcePorts[sourcePorts.length - 2]), reason: 'the first attempt reused a pooled socket');
    expect(pooled, isNot(contains(sourcePorts.last)), reason: 'the retry must not reuse a sibling socket');
  });

  test('stopping requests does not evict an unrelated upload awaiting its response', () async {
    final healthy = outcome(start('/stall'));
    await untilStalled(1);

    for (var i = 0; i < 5; i++) {
      final abort = Completer<void>();
      final cancelled = outcome(manager.sendStreaming(
        http.AbortableRequest('POST', baseUri.resolve('/stall'), abortTrigger: abort.future)..body = 'chat',
      ));
      await untilStalled(i + 2);
      abort.complete();
      expect(await cancelled, isA<http.RequestAbortedException>());
    }

    stalled.first.response.statusCode = HttpStatus.accepted;
    try {
      await stalled.first.response.close();
    } on IOException {
      // The regression closes this healthy peer before its response is ready.
    }
    expect(await healthy, 'answered', reason: 'Chat Stop must not abort another request');
    expect(manager.retiredClientCount, 0, reason: 'intentional cancellation is not a transport failure');
  });

  test('a response-body connection failure retires idle sibling sockets', () async {
    final pooled = await fillPool();
    final response = await start('/drop-body');
    expect(response.statusCode, HttpStatus.ok, reason: 'headers already reached the client');
    await expectLater(response.stream.drain<void>(), throwsA(isA<http.ClientException>()));

    expect(await upload(), HttpStatus.accepted);
    expect(pooled, isNot(contains(sourcePorts.last)), reason: 'a body failure must also retire stale sibling sockets');
  });

  test('stopping a response body does not retire the pool', () async {
    final abort = Completer<void>();
    final response = await manager.sendStreaming(
      http.AbortableRequest('POST', baseUri.resolve('/body-waits'), abortTrigger: abort.future),
    );
    abort.complete();
    await expectLater(response.stream.drain<void>(), throwsA(isA<http.RequestAbortedException>()));

    expect(manager.retiredClientCount, 0);
    expect(await upload(), HttpStatus.accepted);
  });

  test('stream observation preserves response metadata and final redirected URL', () async {
    final response = await start('/redirect');

    expect(response.statusCode, HttpStatus.ok);
    expect(response.contentLength, 5);
    expect(response.headers['x-network-test'], 'kept');
    expect(response.reasonPhrase, 'OK');
    expect(response.persistentConnection, isTrue);
    expect(response.isRedirect, isFalse);
    expect(response.request?.url, baseUri.resolve('/redirect'));
    expect(response, isA<http.BaseResponseWithUrl>());
    expect((response as http.BaseResponseWithUrl).url, baseUri.resolve('/stream'));
    expect(await response.stream.expand((chunk) => chunk).toList(), [0, 1, 2, 3, 4]);
    expect(manager.retiredClientCount, 0);
  });

  test('delayed headers and an active response stream survive repeated resets', () async {
    final slow = start('/slow-headers');
    final streamed = await start('/stream');
    final chunks = <int>[];
    final reading = streamed.stream.listen((chunk) => chunks.addAll(chunk)).asFuture<void>();

    for (var i = 0; i < 3; i++) {
      manager.resetConnections();
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }

    expect((await slow).statusCode, HttpStatus.accepted);
    await reading;
    expect(chunks, [0, 1, 2, 3, 4], reason: 'a retired pool lets its open response stream finish');
  });

  test('a request stalled on a retired pool is closed at its deadline', () async {
    final short = HttpPoolManager.forTesting(retiredGrace: const Duration(milliseconds: 300));
    addTearDown(short.dispose);
    final awaitingHeaders = start('/stall', on: short);
    await untilStalled(1);
    expect(await outcome(awaitingHeaders, within: const Duration(milliseconds: 500)), 'still open');

    short.resetConnections();

    expect(await outcome(awaitingHeaders), isA<http.ClientException>());
    expect(short.retiredClientCount, 0);
  });

  test('a TLS handshake to a silent peer ends at the connection timeout', () async {
    // Closing a pool cannot stop a handshake on an established socket, so the
    // connection timeout is what bounds it.
    final short = HttpPoolManager.forTesting(connectTimeout: const Duration(milliseconds: 300));
    addTearDown(short.dispose);
    final silent = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final peers = <Socket>[];
    silent.listen(peers.add);
    addTearDown(() async {
      for (final peer in peers) {
        peer.destroy();
      }
      await silent.close();
    });

    final inHandshake =
        short.sendStreaming(http.Request('GET', Uri.parse('https://127.0.0.1:${silent.port}/v2/sync-local-files')));

    expect(await outcome(inHandshake), isA<http.ClientException>());
    expect(peers, hasLength(1), reason: 'TCP connected; only the handshake stalled');
  });

  test('a late failure from a retired pool leaves the current pool in place', () async {
    final retiredRequest = start('/stall');
    await untilStalled(1);
    manager.resetConnections();
    await upload();
    final current = sourcePorts.last;

    final socket = await stalled.single.response.detachSocket(writeHeaders: false);
    socket.destroy();
    expect(await outcome(retiredRequest), isA<http.ClientException>());

    await upload();
    expect(sourcePorts.last, current, reason: 'the current pool keeps its socket');
  });

  test('a reset storm keeps at most maxRetiredClients pools and closes the oldest', () async {
    final oldest = start('/stall');
    await untilStalled(1);

    for (var i = 0; i < 10; i++) {
      manager.resetConnections();
    }

    expect(manager.retiredClientCount, HttpPoolManager.maxRetiredClients);
    expect(await outcome(oldest), isA<http.ClientException>(), reason: 'the evicted pool is closed, not dropped');
  });

  test('dispose closes the current and every retired pool', () async {
    final first = start('/stall');
    await untilStalled(1);
    manager.resetConnections();
    final second = start('/stall');
    await untilStalled(2);
    manager.resetConnections();
    final current = start('/stall');
    await untilStalled(3);

    manager.dispose();

    final outcomes = await Future.wait([outcome(first), outcome(second), outcome(current)]);
    expect(outcomes, everyElement(isA<http.ClientException>()));
    expect(manager.retiredClientCount, 0, reason: 'a late failure after dispose must not start a new pool');
  });
}
