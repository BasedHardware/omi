import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/services/sockets/pure_streaming_stt.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a control message reaches the service as a JSON text frame, in order with the audio', () async {
    // A real local WebSocket service: what it receives is what a Custom live provider receives.
    final received = <dynamic>[];
    final gotThree = Completer<void>();
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    server.listen((request) async {
      final ws = await WebSocketTransformer.upgrade(request);
      ws.listen((message) {
        received.add(message);
        if (received.length == 3 && !gotThree.isCompleted) gotThree.complete();
      });
    });

    final socket = PureStreamingSttSocket(
      config: StreamingSttConfig.schemaBased(
        wsUrl: 'ws://127.0.0.1:${server.port}/v1/listen',
        schema: const SttResponseSchema(),
        serviceId: 'customLive',
      ),
    );
    expect(await socket.connect(), isTrue);
    addTearDown(socket.stop);

    socket.send(Uint8List.fromList([1, 2, 3, 4]));
    expect(socket.sendControl({'type': 'ButtonEvent', 'state': 1, 'timestamp': 1731542400000}), isTrue);
    socket.send(Uint8List.fromList([5, 6]));
    await gotThree.future.timeout(const Duration(seconds: 5));

    expect(received[0], [1, 2, 3, 4]);
    expect(received[1], isA<String>());
    expect(jsonDecode(received[1] as String), {'type': 'ButtonEvent', 'state': 1, 'timestamp': 1731542400000});
    expect(received[2], [5, 6]);
  });

  test('a control message is not sent before the socket connects', () {
    final socket = PureStreamingSttSocket(
      config: StreamingSttConfig.schemaBased(wsUrl: 'ws://127.0.0.1:1/v1/listen', schema: const SttResponseSchema()),
    );

    expect(socket.sendControl({'type': 'ButtonEvent', 'state': 1}), isFalse);
  });
}
