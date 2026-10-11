import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/auth/auth_token_result.dart';

class _Listener implements IPureSocketListener {
  int connected = 0;
  int closed = 0;
  final messages = <dynamic>[];
  Completer<void>? messageReceived;
  Completer<void>? connectionClosed;
  void Function()? onConnect;

  @override
  void onConnected() {
    connected++;
    onConnect?.call();
  }

  @override
  void onClosed([int? code]) {
    closed++;
    if (!(connectionClosed?.isCompleted ?? true)) connectionClosed!.complete();
  }

  @override
  void onMessage(dynamic message) {
    messages.add(message);
    if (!(messageReceived?.isCompleted ?? true)) messageReceived!.complete();
  }

  @override
  void onError(Object error, StackTrace trace) => fail('Unexpected socket error: $error');
}

void main() {
  late HttpServer server;
  late List<WebSocket> peers;
  late List<Completer<void>> peerClosed;
  late PureSocket socket;
  late _Listener listener;
  late int upgrades;
  Future<void> Function(HttpRequest)? beforeUpgrade;
  late bool rejectHandshake;

  setUp(() async {
    peers = [];
    peerClosed = [];
    upgrades = 0;
    beforeUpgrade = null;
    rejectHandshake = false;
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((request) async {
      await beforeUpgrade?.call(request);
      if (rejectHandshake) {
        request.response.statusCode = HttpStatus.serviceUnavailable;
        await request.response.close();
        return;
      }
      final peer = await WebSocketTransformer.upgrade(request);
      peers.add(peer);
      upgrades++;
      final closed = Completer<void>();
      peerClosed.add(closed);
      peer.listen((message) => peer.add(message), onDone: closed.complete);
    });
    socket = PureSocket('ws://127.0.0.1:${server.port}', headersProvider: () async => {});
    listener = _Listener();
    socket.setListener(listener);
  });

  tearDown(() async {
    await socket.stop();
    for (final peer in peers) {
      unawaited(peer.close());
    }
    await server.close(force: true);
  });

  test('stop during auth opens no connection after credentials arrive', () async {
    final headers = Completer<Map<String, String>>();
    socket = PureSocket('ws://127.0.0.1:${server.port}', headersProvider: () => headers.future);
    socket.setListener(listener);
    final pending = socket.connect();
    await socket.stop();
    headers.complete({});

    final connected = await pending;
    expect(
      {'connected': connected, 'upgrades': upgrades, 'connectedCallbacks': listener.connected},
      {'connected': false, 'upgrades': 0, 'connectedCallbacks': 0},
      reason: 'A stopped session must perform no network handshake',
    );
    expect(socket.status, PureSocketStatus.disconnected);
  });

  test('concurrent connects reserve ownership before awaiting auth', () async {
    final headers = Completer<Map<String, String>>();
    var authCalls = 0;
    socket = PureSocket('ws://127.0.0.1:${server.port}', headersProvider: () {
      authCalls++;
      return headers.future;
    });
    socket.setListener(listener);
    final first = socket.connect();
    final second = socket.connect();
    headers.complete({});
    // Keep both outcomes so the regression reports actual network work even
    // if the broken implementation also double-subscribes to a channel.
    Future<Object> outcome(Future<bool> attempt) => attempt.then<Object>((value) => value, onError: (Object e) => e);
    final results = await Future.wait([outcome(first), outcome(second)]);

    expect({'authCalls': authCalls, 'upgrades': upgrades}, {'authCalls': 1, 'upgrades': 1});
    expect(results, [true, false]);
    expect(listener.connected, 1);
  });

  test('stop during handshake closes the late channel without publishing capture', () async {
    final requested = Completer<void>();
    final allowUpgrade = Completer<void>();
    beforeUpgrade = (_) {
      requested.complete();
      return allowUpgrade.future;
    };
    final pending = socket.connect();
    await requested.future;
    await socket.stop();
    allowUpgrade.complete();

    expect(await pending, isFalse);
    expect(listener.connected, 0);
    expect(socket.status, PureSocketStatus.disconnected);
    await peerClosed.single.future.timeout(const Duration(seconds: 5));
    expect(listener.closed, 1);
  });

  test('a retired auth completion cannot replace a recovered connection', () async {
    final oldHeaders = Completer<Map<String, String>>();
    var calls = 0;
    socket = PureSocket('ws://127.0.0.1:${server.port}', headersProvider: () {
      return ++calls == 1 ? oldHeaders.future : Future.value({});
    });
    socket.setListener(listener);
    final old = socket.connect();
    await socket.stop();
    expect(await socket.connect(), isTrue);
    oldHeaders.complete({});
    expect(await old, isFalse);
    expect(upgrades, 1);
    expect(socket.status, PureSocketStatus.connected);
    expect(listener.connected, 1);
  });

  test('a retired auth failure cannot reset a recovered connection', () async {
    final oldHeaders = Completer<Map<String, String>>();
    var calls = 0;
    socket = PureSocket('ws://127.0.0.1:${server.port}', headersProvider: () {
      return ++calls == 1 ? oldHeaders.future : Future.value({});
    });
    socket.setListener(listener);
    final old = socket.connect();
    await socket.stop();
    expect(await socket.connect(), isTrue);
    oldHeaders.completeError(AuthTokenUnavailableException(const AuthTokenTransientFailure(failureClass: 'offline')));
    expect(await old, isFalse);
    expect(socket.status, PureSocketStatus.connected);
    expect(upgrades, 1);
  });

  test('a late handshake and its close cannot disturb a recovered connection', () async {
    final requested = Completer<void>();
    final allowUpgrade = Completer<void>();
    beforeUpgrade = (_) {
      requested.complete();
      return allowUpgrade.future;
    };
    final old = socket.connect();
    await requested.future;
    await socket.stop();
    beforeUpgrade = null;
    expect(await socket.connect(), isTrue);
    allowUpgrade.complete();
    expect(await old, isFalse);
    await peerClosed.last.future.timeout(const Duration(seconds: 5));
    expect(listener.closed, 1);
    expect(listener.connected, 1);
    expect(socket.status, PureSocketStatus.connected);
    listener.messageReceived = Completer<void>();
    socket.send([5, 6, 7]);
    await listener.messageReceived!.future;
    expect(listener.messages.single, [5, 6, 7]);
  });

  test('failed handshake releases the attempt and a subsequent retry carries audio', () async {
    rejectHandshake = true;
    expect(await socket.connect(), isFalse);
    expect(socket.status, isNot(PureSocketStatus.connecting));
    rejectHandshake = false;
    expect(await socket.connect(), isTrue);
    listener.messageReceived = Completer<void>();
    socket.send([8, 9]);
    await listener.messageReceived!.future;
    expect(listener.messages.single, [8, 9]);
    expect(upgrades, 1);
  });

  test('unexpected auth errors release the attempt for retry', () async {
    var calls = 0;
    socket = PureSocket('ws://127.0.0.1:${server.port}', headersProvider: () async {
      if (++calls == 1) throw StateError('synthetic credential failure');
      return {};
    });
    await expectLater(socket.connect(), throwsStateError);
    expect(await socket.connect(), isTrue);
    expect(upgrades, 1);
  });

  test('synchronous stop from onConnected closes once and does not retain a channel', () async {
    listener.onConnect = () => unawaited(socket.stop());
    expect(await socket.connect(), isFalse);
    await peerClosed.single.future.timeout(const Duration(seconds: 5));
    await socket.stop();
    expect(listener.closed, 1);
    expect(socket.status, PureSocketStatus.disconnected);
    expect(() => socket.channel, throwsException);
  });

  test('live audio and transcript survive remote close followed by reconnect', () async {
    expect(await socket.connect(), isTrue);
    listener.messageReceived = Completer<void>();
    socket.send([1, 2, 3, 4]);
    await listener.messageReceived!.future;
    expect(listener.messages.single, [1, 2, 3, 4]);

    listener.connectionClosed = Completer<void>();
    unawaited(peers.single.close(WebSocketStatus.goingAway));
    await listener.connectionClosed!.future;
    expect(await socket.connect(), isTrue);
    listener.messageReceived = Completer<void>();
    socket.send('synthetic transcript after recovery');
    await listener.messageReceived!.future;
    expect(listener.messages.last, 'synthetic transcript after recovery');
    expect(upgrades, 2);
    expect(listener.connected, 2);
    await socket.stop();
    await peerClosed.last.future.timeout(const Duration(seconds: 5));
  });
}
