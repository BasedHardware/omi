import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/phone_call_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channelName = 'com.omi/phone_calls/events';
  const codec = StandardMethodCodec();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  Future<void> emitEvent(Object? event) {
    return messenger.handlePlatformMessage(
      channelName,
      codec.encodeSuccessEnvelope(event),
      (ByteData? data) {},
    );
  }

  setUp(() {
    messenger.setMockMessageHandler(channelName, (ByteData? message) async {
      return codec.encodeSuccessEnvelope(null);
    });
  });

  tearDown(() {
    messenger.setMockMessageHandler(channelName, null);
  });

  group('PhoneCallService audio event delivery', () {
    late PhoneCallService service;
    final delivered = <(Uint8List, int)>[];

    setUp(() {
      service = PhoneCallService();
      delivered.clear();
      service.onAudioData = (data, channel) => delivered.add((data, channel));
    });

    tearDown(() => service.dispose());

    test('Uint8List audio events deliver frames verbatim over the channel', () async {
      service.startListening();
      await emitEvent({
        'type': 'audioData',
        'data': Uint8List.fromList([1, 2, 3]),
        'channel': 1
      });
      await emitEvent({
        'type': 'audioData',
        'data': Uint8List.fromList([9, 8]),
        'channel': 2
      });
      await Future<void>.delayed(Duration.zero);

      expect(delivered.length, 2);
      expect(delivered[0].$1, Uint8List.fromList([1, 2, 3]));
      expect(delivered[0].$2, 1);
      expect(delivered[1].$2, 2);
    });

    test('data as generic List (platform codec int list) is coerced and delivered', () {
      service.handleEventForTesting({
        'type': 'audioData',
        'data': <dynamic>[4, 5, 6],
        'channel': 1
      });

      expect(delivered.length, 1);
      expect(delivered[0].$1, Uint8List.fromList([4, 5, 6]));
      expect(service.eventChannelCoerced, greaterThanOrEqualTo(1));
    });

    test('data as Int8List is reinterpreted to bytes and delivered', () {
      service.handleEventForTesting({
        'type': 'audioData',
        'data': Int8List.fromList([-1, 2, -3]),
        'channel': 1,
      });

      expect(delivered.length, 1);
      // Two's complement reinterpretation: -1 -> 255, -3 -> 253.
      expect(delivered[0].$1, Uint8List.fromList([255, 2, 253]));
    });

    test('data as List<int> is delivered', () {
      service.handleEventForTesting({
        'type': 'audioData',
        'data': <int>[10, 20, 30, 40],
        'channel': 2,
      });

      expect(delivered.length, 1);
      expect(delivered[0].$1, Uint8List.fromList([10, 20, 30, 40]));
      expect(delivered[0].$2, 2);
    });

    test('undecodable data is counted and dropped, not thrown', () {
      service.handleEventForTesting({'type': 'audioData', 'data': 'not-bytes', 'channel': 1});

      expect(delivered, isEmpty);
      expect(service.eventChannelErrors, 1);
    });

    test('channel as non-int is coerced', () {
      service.handleEventForTesting({
        'type': 'audioData',
        'data': [1],
        'channel': '2'
      });

      expect(delivered.length, 1);
      expect(delivered[0].$2, 2);
    });

    test('a callback that throws does not unsubscribe — later events still arrive', () {
      var calls = 0;
      service.onAudioData = (data, channel) {
        calls++;
        if (calls == 1) throw StateError('listener blew up');
      };

      service.handleEventForTesting({
        'type': 'audioData',
        'data': [1],
        'channel': 1
      });
      service.handleEventForTesting({
        'type': 'audioData',
        'data': [2],
        'channel': 1
      });

      expect(calls, 2, reason: 'the second event must still be delivered after a throw');
      expect(service.eventChannelErrors, 1);
    });
  });
}
