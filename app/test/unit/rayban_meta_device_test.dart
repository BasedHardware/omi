import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/discovery/rayban_meta_discoverer.dart';
import 'package:omi/services/devices/transports/rayban_meta_transport.dart';

void main() {
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
