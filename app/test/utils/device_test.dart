import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/device.dart';

void main() {
  // DevKit boards enumerate as DeviceType.omi like the consumer pendant, so the
  // device-onboarding gate distinguishes them via model number / advertised name.
  group('DeviceUtils.isOmiDevKit', () {
    test('detects DevKit 2 by model number', () {
      expect(DeviceUtils.isOmiDevKit(modelNumber: 'OMI DEVKIT 2'), isTrue);
    });

    test('detects DevKit by advertised name', () {
      expect(DeviceUtils.isOmiDevKit(deviceName: 'Omi DevKit'), isTrue);
    });

    test('is case-insensitive', () {
      expect(DeviceUtils.isOmiDevKit(modelNumber: 'omi devkit 2'), isTrue);
    });

    test('consumer pendant is NOT a DevKit', () {
      expect(DeviceUtils.isOmiDevKit(modelNumber: 'Omi', deviceName: 'Omi'), isFalse);
    });

    test("default 'Omi Device' fallback is NOT a DevKit (contains DEV but not DEVKIT)", () {
      expect(DeviceUtils.isOmiDevKit(modelNumber: 'Omi Device', deviceName: 'Omi'), isFalse);
    });

    test('Neo consumer device is NOT a DevKit', () {
      expect(DeviceUtils.isOmiDevKit(modelNumber: 'Omi Neo', deviceName: 'Neo'), isFalse);
    });

    test('null / empty inputs are NOT a DevKit', () {
      expect(DeviceUtils.isOmiDevKit(), isFalse);
      expect(DeviceUtils.isOmiDevKit(modelNumber: '', deviceName: ''), isFalse);
    });
  });
}
