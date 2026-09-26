import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/sockets/pure_socket.dart';

void main() {
  test('unavailable auth blocks a socket before opening the network', () async {
    final socket = PureSocket(
      'wss://example.invalid',
      headersProvider: () async {
        throw AuthTokenUnavailableException(const AuthTokenTransientFailure(failureClass: 'offline'));
      },
    );

    expect(await socket.connect(), isFalse);
    expect(socket.status, PureSocketStatus.notConnected);
  });

  test('merges extra headers with a custom provider', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final headersSeen = Completer<Map<String, String>>();
    server.listen((request) async {
      final webSocket = await WebSocketTransformer.upgrade(request);
      headersSeen.complete({
        'extra': request.headers.value('x-extra') ?? '',
        'provider': request.headers.value('x-provider') ?? '',
      });
      await webSocket.close();
    });
    addTearDown(() => server.close(force: true));

    final socket = PureSocket(
      'ws://${InternetAddress.loopbackIPv4.address}:${server.port}',
      headersProvider: () async => {'x-provider': 'provider'},
      extraHeaders: const {'x-extra': 'extra', 'x-provider': 'override'},
    );

    expect(await socket.connect(), isTrue);
    expect(await headersSeen.future, {'extra': 'extra', 'provider': 'override'});
    await socket.disconnect();
  });
}
