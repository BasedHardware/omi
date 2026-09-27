import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';

class _FakeSocket implements IPureSocket {
  @override
  PureSocketStatus status = PureSocketStatus.connected;
  final List<dynamic> sent = [];
  IPureSocketListener? listener;
  bool dropOnSend = false;

  @override
  Future<bool> connect() async => true;

  @override
  Future<void> disconnect() async {}

  @override
  void onClosed() => listener?.onClosed();

  @override
  void onConnected() => listener?.onConnected();

  @override
  void onError(Object err, StackTrace trace) {}

  @override
  void onMessage(dynamic message) {}

  @override
  void send(dynamic message) {
    sent.add(message);
    if (dropOnSend) status = PureSocketStatus.notConnected;
  }

  @override
  void setListener(IPureSocketListener l) => listener = l;

  @override
  Future<void> stop() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  TranscriptSegmentSocketService serviceFor(_FakeSocket socket) =>
      TranscriptSegmentSocketService.withSocket(16000, BleAudioCodec.opus, 'en', socket);

  group('TranscriptSegmentSocketService binary byte counting', () {
    test('counts List<int> frames sent while connected', () async {
      final socket = _FakeSocket();
      final service = serviceFor(socket);

      await service.send(List<int>.filled(320, 1));
      await service.send(List<int>.filled(80, 1));

      expect(service.binaryAudioBytesSent, 400);
    });

    test('does not count JSON control frames', () async {
      final socket = _FakeSocket();
      final service = serviceFor(socket);

      await service.send(jsonEncode({'type': 'start_onboarding'}));
      await service.sendText(jsonEncode({'type': 'ping'}));
      await service.send('plain string');

      expect(service.binaryAudioBytesSent, 0);
      expect(socket.sent, hasLength(3));
    });

    test('does not count frames enqueued while disconnected', () async {
      final socket = _FakeSocket()..status = PureSocketStatus.notConnected;
      final service = serviceFor(socket);

      await service.send(List<int>.filled(320, 1));

      expect(service.binaryAudioBytesSent, 0);
    });

    test('does not count a frame when the socket drops mid-send', () async {
      final socket = _FakeSocket()..dropOnSend = true;
      final service = serviceFor(socket);

      await service.send(List<int>.filled(320, 1));

      expect(service.binaryAudioBytesSent, 0);
    });

    test('resumes counting after the socket recovers', () async {
      final socket = _FakeSocket();
      final service = serviceFor(socket);

      socket.status = PureSocketStatus.notConnected;
      await service.send(List<int>.filled(100, 1));
      socket.status = PureSocketStatus.connected;
      await service.send(List<int>.filled(50, 1));

      expect(service.binaryAudioBytesSent, 50);
    });

    test('stop() marks the teardown as intentional', () async {
      final service = serviceFor(_FakeSocket());
      expect(service.stoppedIntentionally, isFalse);
      await service.stop();
      expect(service.stoppedIntentionally, isTrue);
    });

    test('a reconnect resets the counter and intent flag for the next session', () async {
      final socket = _FakeSocket();
      final service = serviceFor(socket);

      socket.onConnected();
      await service.send(List<int>.filled(320, 1));
      expect(service.binaryAudioBytesSent, 320);

      socket.status = PureSocketStatus.disconnected;
      socket.onClosed();
      socket.status = PureSocketStatus.connected;
      socket.onConnected();

      expect(service.binaryAudioBytesSent, 0);
      expect(service.stoppedIntentionally, isFalse);

      await service.send(List<int>.filled(100, 1));
      expect(service.binaryAudioBytesSent, 100);
    });

    test('a reconnect after a deliberate stop clears the intentional flag', () async {
      final socket = _FakeSocket();
      final service = serviceFor(socket);

      socket.onConnected();
      await service.stop();
      expect(service.stoppedIntentionally, isTrue);

      socket.status = PureSocketStatus.connected;
      socket.onConnected();
      expect(service.stoppedIntentionally, isFalse);
    });
  });
}
