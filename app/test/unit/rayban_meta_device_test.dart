import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/discovery/rayban_meta_discoverer.dart';
import 'package:omi/services/devices/transports/rayban_meta_transport.dart';

const _rayBanMetaHostApiPrefix = 'dev.flutter.pigeon.omi_pigeon.RayBanMetaHostAPI';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final hostApiChannelNames = <String>{};

  void setRayBanMetaHostApiHandler(String methodName, Future<Object?> Function(Object? message) handler) {
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    final channelName = '$_rayBanMetaHostApiPrefix.$methodName';
    hostApiChannelNames.add(channelName);
    messenger.setMockMessageHandler(channelName, (ByteData? message) async {
      final decoded = RayBanMetaHostAPI.pigeonChannelCodec.decodeMessage(message);
      final response = await handler(decoded);
      return RayBanMetaHostAPI.pigeonChannelCodec.encodeMessage(response);
    });
  }

  tearDown(() {
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    for (final channelName in hostApiChannelNames) {
      messenger.setMockMessageHandler(channelName, null);
    }
    hostApiChannelNames.clear();
  });

  group('DeviceType.raybanMeta serialization', () {
    test('round-trips by name through BtDevice json', () {
      final device = BtDevice(
        name: 'Ray-Ban Meta',
        id: 'meta-glasses-1',
        type: DeviceType.raybanMeta,
        rssi: 0,
        locator: DeviceLocator.metaDat(),
      );

      final json = device.toJson();
      expect(json['type'], 'raybanMeta');

      final restored = BtDevice.fromJson(json);
      expect(restored.type, DeviceType.raybanMeta);
      expect(restored.id, 'meta-glasses-1');
      expect(restored.locator?.kind, TransportKind.metaDat);
    });

    test('deserializes from legacy integer index', () {
      final device = BtDevice.fromJson({
        'name': 'Ray-Ban Meta',
        'id': 'meta-glasses-1',
        'type': 9, // index in _legacyDeviceTypeNames
        'rssi': 0,
      });
      expect(device.type, DeviceType.raybanMeta);
    });

    test('unknown type name still falls back to omi', () {
      final device = BtDevice.fromJson({'name': 'x', 'id': 'y', 'type': 'notADevice', 'rssi': 0});
      expect(device.type, DeviceType.omi);
    });

    test('has no firmware warnings', () {
      final device = BtDevice(name: 'Ray-Ban Meta', id: 'id', type: DeviceType.raybanMeta, rssi: 0);
      expect(device.getFirmwareWarningTitle(), isEmpty);
      expect(device.getFirmwareWarningMessage(), isEmpty);
    });
  });

  group('DeviceLocator.metaDat', () {
    test('round-trips with audio-only extra', () {
      final locator = DeviceLocator.metaDat(extras: const {RayBanMetaDiscoverer.audioOnlyExtraKey: true});
      final restored = DeviceLocator.fromJson(locator.toJson());
      expect(restored.kind, TransportKind.metaDat);
      expect(restored.extras[RayBanMetaDiscoverer.audioOnlyExtraKey], true);
    });
  });

  group('DeviceLocator.fromJson robustness', () {
    test('invalid or out-of-range kind falls back instead of throwing', () {
      final outOfRange = DeviceLocator.fromJson({'kind': 99, 'extras': {}});
      expect(outOfRange.kind, TransportKind.bluetooth);

      final wrongType = DeviceLocator.fromJson({'kind': 'bogus', 'bluetoothId': 'abc'});
      expect(wrongType.kind, TransportKind.bluetooth);
      expect(wrongType.bluetoothId, 'abc');

      final missingId = DeviceLocator.fromJson({'kind': 0});
      expect(missingId.bluetoothId, isNull);

      final blankId = DeviceLocator.fromJson({'kind': 0, 'bluetoothId': '   '});
      expect(blankId.bluetoothId, isNull);
    });

    test('corrupted bluetooth locators without ids are not connectable', () {
      final missingIdDevice = BtDevice(
        name: 'Corrupted BLE',
        id: 'fallback-id',
        type: DeviceType.omi,
        rssi: 0,
        locator: DeviceLocator.fromJson({'kind': 99}),
      );
      expect(DeviceConnectionFactory.create(missingIdDevice), isNull);

      final blankIdDevice = BtDevice(
        name: 'Blank BLE',
        id: 'fallback-id',
        type: DeviceType.omi,
        rssi: 0,
        locator: DeviceLocator.fromJson({'kind': 0, 'bluetoothId': ''}),
      );
      expect(DeviceConnectionFactory.create(blankIdDevice), isNull);
    });
  });

  group('ConversationSource.rayban_meta', () {
    test('parses from backend source string', () {
      expect(ConversationSource.values.asNameMap()['rayban_meta'], ConversationSource.rayban_meta);
    });
  });

  group('RayBanMeta photo event framing', () {
    test('carries orientation byte plus jpeg payload', () {
      final jpeg = Uint8List.fromList([0xFF, 0xD8, 0xFF, 0xE0, 1, 2, 3]);
      final framed = RayBanMetaTransport.framePhotoEvent(jpeg, 180);

      expect(framed.first, 2); // 180° / 90
      expect(framed.sublist(1), jpeg);
      expect(ImageOrientation.fromValue(framed.first), ImageOrientation.orientation180);
    });

    test('clamps unexpected orientation degrees into range', () {
      final jpeg = Uint8List.fromList([0xFF, 0xD8]);
      expect(RayBanMetaTransport.framePhotoEvent(jpeg, 360).first, 0); // 4 & 0x03
      expect(RayBanMetaTransport.framePhotoEvent(jpeg, 0).first, 0);
      expect(RayBanMetaTransport.framePhotoEvent(jpeg, 90).first, 1);
    });
  });

  group('RayBanMetaTransport disconnect', () {
    test('continues native teardown when stopping audio fails', () async {
      final nativeCalls = <String>[];

      setRayBanMetaHostApiHandler('getAvailabilityMode', (_) async => <Object?>['audio_only']);
      setRayBanMetaHostApiHandler(
        'getBluetoothHfpInputNames',
        (_) async => <Object?>[
          <Object?>['Ray-Ban Meta'],
        ],
      );
      setRayBanMetaHostApiHandler('stopAudioCapture', (_) async {
        nativeCalls.add('stopAudioCapture');
        return <Object?>['audio-stop-failed', 'Audio teardown failed', null];
      });
      setRayBanMetaHostApiHandler('stopCamera', (_) async {
        nativeCalls.add('stopCamera');
        return <Object?>[];
      });
      setRayBanMetaHostApiHandler('disconnect', (_) async {
        nativeCalls.add('disconnect');
        return <Object?>[];
      });

      final transport = RayBanMetaTransport('rayban-meta-test');
      await transport.connect();

      await expectLater(transport.disconnect(), completes);
      expect(nativeCalls, ['stopAudioCapture', 'stopCamera', 'disconnect']);
      expect(await transport.isConnected(), isTrue);
    });
  });

  group('RayBanMetaDiscoverer audio-only matching', () {
    test('matches Meta product names precisely, not generic glasses', () {
      expect(RayBanMetaDiscoverer.looksLikeMetaGlasses("Eulices's Ray-Ban Meta"), isTrue);
      expect(RayBanMetaDiscoverer.looksLikeMetaGlasses('RayBan Meta Smart Glasses'), isTrue);
      expect(RayBanMetaDiscoverer.looksLikeMetaGlasses('Oakley Meta HSTN'), isTrue);
      expect(RayBanMetaDiscoverer.looksLikeMetaGlasses('Meta Glasses'), isTrue);

      // Must not swallow other glasses/audio devices.
      expect(RayBanMetaDiscoverer.looksLikeMetaGlasses('OmiGlass'), isFalse);
      expect(RayBanMetaDiscoverer.looksLikeMetaGlasses('OpenGlass'), isFalse);
      expect(RayBanMetaDiscoverer.looksLikeMetaGlasses('AirPods Pro'), isFalse);
      expect(RayBanMetaDiscoverer.looksLikeMetaGlasses('Car Audio'), isFalse);
    });
  });
}
