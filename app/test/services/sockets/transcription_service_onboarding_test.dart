import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';

class _FakeSocket implements IPureSocket {
  dynamic sentMessage;
  IPureSocketListener? listener;

  @override
  PureSocketStatus get status => PureSocketStatus.connected;

  @override
  Future<bool> connect() async => true;

  @override
  Future<void> disconnect() async {}

  @override
  void onClosed() {}

  @override
  void onConnected() {}

  @override
  void onError(Object err, StackTrace trace) {}

  @override
  void onMessage(dynamic message) {}

  @override
  void send(dynamic message) => sentMessage = message;

  @override
  void setListener(IPureSocketListener listener) => this.listener = listener;

  @override
  Future<void> stop() async {}
}

void main() {
  test('serializes the explicit onboarding start request', () async {
    final socket = _FakeSocket();
    final service = TranscriptSegmentSocketService.withSocket(16000, BleAudioCodec.pcm16, 'en', socket);

    await service.requestFirstOnboardingQuestion();

    expect(socket.sentMessage, '{"type":"start_onboarding"}');
  });
}
