import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/device_storage_routing.dart';

BtDevice _device(DeviceType type, {String firmware = 'Unknown'}) =>
    BtDevice(name: type.name, id: 'device-id', type: type, rssi: -40, firmwareRevision: firmware);

void main() {
  group('DeviceStorageProtocolPolicy', () {
    test('storage-authoritative audio is exact to the 3.0.29 test line', () {
      expect(DeviceStorageProtocolPolicy.usesStorageAuthoritativeAudio('3.0.28'), isFalse);
      expect(DeviceStorageProtocolPolicy.usesStorageAuthoritativeAudio('3.0.29'), isTrue);
      expect(DeviceStorageProtocolPolicy.usesStorageAuthoritativeAudio('3.0.29+7'), isTrue);
      expect(DeviceStorageProtocolPolicy.usesStorageAuthoritativeAudio('3.0.30'), isFalse);
      expect(DeviceStorageProtocolPolicy.usesStorageAuthoritativeAudio('Unknown'), isFalse);
    });

    test('internal harness admits 3.0.30 without widening production policy', () {
      expect(DeviceStorageProtocolPolicy.usesStorageAuthoritativeAudio('3.0.30'), isFalse);
      expect(
        DeviceStorageProtocolPolicy.usesStorageAuthoritativeAudio(
          '3.0.30+110',
          allowBlackboxDiagnosticsFirmware: true,
        ),
        isTrue,
      );
      expect(
        DeviceStorageProtocolPolicy.usesStorageAuthoritativeAudio(
          '3.0.31',
          allowBlackboxDiagnosticsFirmware: true,
        ),
        isFalse,
      );
    });

    test('enriched firmware wins over a raw Unknown connect object', () {
      expect(DeviceStorageProtocolPolicy.resolveFirmware('3.0.20', 'Unknown'), '3.0.20');
      expect(
        DeviceStorageProtocolPolicy.classify(_device(DeviceType.omi), firmwareVersion: '3.0.20'),
        DeviceStorageProtocol.ringBuffer,
      );
    });

    test('routes each supported Omi firmware generation to exactly one protocol', () {
      expect(
        DeviceStorageProtocolPolicy.classify(_device(DeviceType.omi, firmware: '3.0.16')),
        DeviceStorageProtocol.legacySdCard,
      );
      expect(
        DeviceStorageProtocolPolicy.classify(_device(DeviceType.omi, firmware: '3.0.19')),
        DeviceStorageProtocol.multiFile,
      );
      expect(
        DeviceStorageProtocolPolicy.classify(_device(DeviceType.omi, firmware: '3.0.20')),
        DeviceStorageProtocol.ringBuffer,
      );
      expect(
        DeviceStorageProtocolPolicy.classify(_device(DeviceType.omi, firmware: '3.0.28+4')),
        DeviceStorageProtocol.ringBuffer,
      );
    });

    test('unknown firmware fails closed instead of probing the legacy protocol', () {
      expect(
        DeviceStorageProtocolPolicy.classify(_device(DeviceType.omi)),
        DeviceStorageProtocol.none,
      );
    });
  });

  group('DeviceStorageRouter ownership', () {
    late List<BtDevice?> legacyBindings;
    late List<BtDevice?> multiFileBindings;
    late List<BtDevice?> ringBindings;
    late List<BtDevice?> limitlessBindings;
    late DeviceStorageRouter router;

    setUp(() {
      legacyBindings = [];
      multiFileBindings = [];
      ringBindings = [];
      limitlessBindings = [];
      router = DeviceStorageRouter(
        bindLegacySdCard: legacyBindings.add,
        bindMultiFile: multiFileBindings.add,
        bindRingBuffer: ringBindings.add,
        bindLimitlessFlash: limitlessBindings.add,
      );
    });

    test('ring firmware disconnects every incompatible parser', () {
      final device = _device(DeviceType.omi, firmware: '3.0.28');

      router.bind(device);

      expect(router.protocol, DeviceStorageProtocol.ringBuffer);
      expect(legacyBindings, [null]);
      expect(multiFileBindings, [null]);
      expect(ringBindings, [same(device)]);
      expect(limitlessBindings, [null]);
    });

    test('switching devices clears the previous owner before binding the new owner', () {
      final ring = _device(DeviceType.omi, firmware: '3.0.28');
      final limitless = _device(DeviceType.limitless);

      router.bind(ring);
      router.bind(limitless);

      expect(ringBindings, [same(ring), null]);
      expect(limitlessBindings, [null, same(limitless)]);
      expect(legacyBindings, [null, null]);
      expect(multiFileBindings, [null, null]);
    });

    test('disconnect clears every protocol owner', () {
      router.bind(_device(DeviceType.omi, firmware: '3.0.16'));
      router.bind(null);

      expect(router.protocol, DeviceStorageProtocol.none);
      expect(legacyBindings.last, isNull);
      expect(multiFileBindings.last, isNull);
      expect(ringBindings.last, isNull);
      expect(limitlessBindings.last, isNull);
    });
  });
}
