import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/device_pairing_roles.dart';

BtDevice _device(String id, {DeviceType type = DeviceType.omi, String name = 'Omi'}) =>
    BtDevice(id: id, name: name, type: type, rssi: -50);

void main() {
  final omi = _device('omi-1');
  final glass = _device('glass-1', type: DeviceType.openglass, name: 'OmiGlass');
  final legacyGlass = _device('glass-2', name: 'OpenGlass'); // advertises as DeviceType.omi

  group('isCameraDevice', () {
    test('recognises OpenGlass by type and legacy glasses by name', () {
      expect(DevicePairingRoles.isCameraDevice(glass), isTrue);
      expect(DevicePairingRoles.isCameraDevice(legacyGlass), isTrue);
      expect(DevicePairingRoles.isCameraDevice(omi), isFalse);
      expect(DevicePairingRoles.isCameraDevice(null), isFalse);
      expect(DevicePairingRoles.isCameraDevice(_device('bee', type: DeviceType.bee, name: 'glass')), isFalse);
    });
  });

  group('canPairAsCompanion', () {
    test('an Omi pendant and an OmiGlass pair with each other in either order', () {
      expect(DevicePairingRoles.canPairAsCompanion(omi, glass), isTrue);
      expect(DevicePairingRoles.canPairAsCompanion(glass, omi), isTrue);
      expect(DevicePairingRoles.canPairAsCompanion(omi, legacyGlass), isTrue);
    });

    test('two pendants or two glasses replace each other instead', () {
      expect(DevicePairingRoles.canPairAsCompanion(omi, _device('omi-2')), isFalse);
      expect(DevicePairingRoles.canPairAsCompanion(glass, legacyGlass), isFalse);
    });

    test('rejects the same device, an empty primary, and non-Omi pendants', () {
      expect(DevicePairingRoles.canPairAsCompanion(omi, omi), isFalse);
      expect(DevicePairingRoles.canPairAsCompanion(_device(''), glass), isFalse);
      expect(DevicePairingRoles.canPairAsCompanion(_device('pendant', type: DeviceType.friendPendant), glass), isFalse);
      expect(DevicePairingRoles.canPairAsCompanion(_device('limitless', type: DeviceType.limitless), glass), isFalse);
    });
  });

  group('role selection', () {
    test('pendant carries audio and glasses carry photos when both are connected', () {
      for (final connected in [
        [omi, glass],
        [glass, omi],
      ]) {
        expect(DevicePairingRoles.selectAudioDevice(connected)?.id, 'omi-1');
        expect(DevicePairingRoles.selectPhotoDevice(connected)?.id, 'glass-1');
      }
    });

    test('glasses alone carry both audio and photos', () {
      expect(DevicePairingRoles.selectAudioDevice([glass])?.id, 'glass-1');
      expect(DevicePairingRoles.selectPhotoDevice([glass])?.id, 'glass-1');
    });

    test('pendant alone carries audio and nothing carries photos', () {
      expect(DevicePairingRoles.selectAudioDevice([omi])?.id, 'omi-1');
      expect(DevicePairingRoles.selectPhotoDevice([omi]), isNull);
    });

    test('no connected devices yields no roles', () {
      expect(DevicePairingRoles.selectAudioDevice(const []), isNull);
      expect(DevicePairingRoles.selectPhotoDevice(const []), isNull);
    });
  });
}
