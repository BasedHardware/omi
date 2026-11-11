import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/firmware_update_build_policy.dart';

void main() {
  group('FirmwareUpdateBuildPolicy', () {
    test('default build keeps Omi firmware updates enabled', () {
      const policy = FirmwareUpdateBuildPolicy(rayBanDat: false);

      expect(policy.allowsOmiFirmwareUpdate, isTrue);
      expect(policy.allowsOpenGlassFirmwareUpdate, isTrue);
    });

    test('Ray-Ban DAT build disables Omi firmware updates only', () {
      const policy = FirmwareUpdateBuildPolicy(rayBanDat: true);

      expect(policy.allowsOmiFirmwareUpdate, isFalse);
      expect(policy.allowsOpenGlassFirmwareUpdate, isTrue);
    });

    test('routes OpenGlass updates independently from native Omi DFU', () {
      const defaultPolicy = FirmwareUpdateBuildPolicy(rayBanDat: false);
      const datPolicy = FirmwareUpdateBuildPolicy(rayBanDat: true);

      expect(defaultPolicy.allowsFirmwareUpdate(isOpenGlass: false), isTrue);
      expect(datPolicy.allowsFirmwareUpdate(isOpenGlass: false), isFalse);
      expect(datPolicy.allowsFirmwareUpdate(isOpenGlass: true), isTrue);
    });

    test('classifies OpenGlass without treating Ray-Ban glasses as OpenGlass', () {
      const policy = FirmwareUpdateBuildPolicy(rayBanDat: true);

      expect(policy.isOpenGlassDevice(_device(type: DeviceType.openglass, name: 'OpenGlass')), isTrue);
      expect(policy.isOpenGlassDevice(_device(type: DeviceType.omi, name: 'OmiGlass')), isTrue);
      expect(policy.isOpenGlassDevice(_device(type: DeviceType.raybanMeta, name: 'Ray-Ban Meta glasses')), isFalse);
    });

    test('never offers Omi firmware UI for Ray-Ban devices', () {
      const defaultPolicy = FirmwareUpdateBuildPolicy(rayBanDat: false);
      const datPolicy = FirmwareUpdateBuildPolicy(rayBanDat: true);
      final rayBan = _device(type: DeviceType.raybanMeta, name: 'Ray-Ban Meta glasses');
      final omi = _device(type: DeviceType.omi, name: 'Omi');
      final openGlass = _device(type: DeviceType.openglass, name: 'OpenGlass');

      expect(defaultPolicy.allowsFirmwareUpdateForDevice(rayBan), isFalse);
      expect(datPolicy.allowsFirmwareUpdateForDevice(rayBan), isFalse);
      expect(defaultPolicy.allowsFirmwareUpdateForDevice(omi), isTrue);
      expect(datPolicy.allowsFirmwareUpdateForDevice(omi), isFalse);
      expect(datPolicy.allowsFirmwareUpdateForDevice(openGlass), isTrue);
    });
  });
}

BtDevice _device({required DeviceType type, required String name}) {
  return BtDevice(name: name, id: 'test-device', type: type, rssi: 0);
}
