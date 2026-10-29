import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/http_pool_manager.dart';

/// Pooled keep-alive sockets outlive a Wi-Fi/cellular switch: uploads a few
/// seconds apart never let one idle out, and iOS then fails the reused socket
/// with EADDRNOTAVAIL ("Can't assign requested address"). These run the real
/// dart:io pool against a loopback server and record which client socket
/// carried each request.
void main() {
  late HttpServer server;
  late Uri uploadUri;
  late List<int> sourcePorts;
  late bool dropNextConnection;

  setUp(() async {
    sourcePorts = [];
    dropNextConnection = false;
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    uploadUri = Uri.parse('http://127.0.0.1:${server.port}/v2/sync-local-files');
    server.listen((request) async {
      sourcePorts.add(request.connectionInfo!.remotePort);
      await request.drain<void>();
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
    HttpPoolManager.instance.resetConnections();
  });

  tearDown(() => server.close(force: true));

  Future<int> upload() async {
    final response = await HttpPoolManager.instance.sendStreaming(http.Request('POST', uploadUri)..body = 'audio');
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

  test('consecutive uploads ride one pooled socket', () async {
    expect(await upload(), HttpStatus.accepted);
    expect(await upload(), HttpStatus.accepted);

    expect(sourcePorts[1], sourcePorts[0]);
  });

  test('after a network switch the next upload opens a new socket', () async {
    await upload();
    HttpPoolManager.instance.resetConnections();
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

    final response = await HttpPoolManager.instance.send(
      () => http.Request('POST', uploadUri)..body = 'audio',
      retries: 1,
    );

    expect(response.statusCode, HttpStatus.accepted);
    expect(pooled, contains(sourcePorts[sourcePorts.length - 2]), reason: 'the first attempt reused a pooled socket');
    expect(pooled, isNot(contains(sourcePorts.last)), reason: 'the retry must not reuse a sibling socket');
  });
}
