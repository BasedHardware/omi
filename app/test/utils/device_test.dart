import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/device.dart';

void main() {
  // The "How to use your Omi" tutorial is CV1-only. Other omi-enumerated
  // variants (DevKit, Glass, Neo, Friend) share DeviceType.omi, so isOmiCv1
  // distinguishes them by GATT model number / advertised name.
  group('DeviceUtils.isOmiCv1', () {
    test('CV1 model is CV1', () {
      expect(DeviceUtils.isOmiCv1(modelNumber: 'Omi CV 1'), isTrue);
    });

    test("default 'Omi Device' fallback is treated as CV1", () {
      expect(DeviceUtils.isOmiCv1(modelNumber: 'Omi Device', deviceName: 'Omi'), isTrue);
    });

    test('DevKit 2 is NOT CV1', () {
      expect(DeviceUtils.isOmiCv1(modelNumber: 'Omi DevKit 2'), isFalse);
    });

    test('DevKit by name is NOT CV1', () {
      expect(DeviceUtils.isOmiCv1(deviceName: 'Omi DevKit'), isFalse);
    });

    test('Friend DevKit 1 is NOT CV1', () {
      expect(DeviceUtils.isOmiCv1(modelNumber: 'Friend DevKit 1'), isFalse);
    });

    test('Glass is NOT CV1', () {
      expect(DeviceUtils.isOmiCv1(modelNumber: 'OMI Glass'), isFalse);
    });

    test('Neo is NOT CV1', () {
      expect(DeviceUtils.isOmiCv1(modelNumber: 'Neo One', deviceName: 'Neo'), isFalse);
    });

    test('is case-insensitive', () {
      expect(DeviceUtils.isOmiCv1(modelNumber: 'omi devkit 2'), isFalse);
    });

    test('null / empty inputs default to CV1 (already gated on DeviceType.omi)', () {
      expect(DeviceUtils.isOmiCv1(), isTrue);
      expect(DeviceUtils.isOmiCv1(modelNumber: '', deviceName: ''), isTrue);
    });
  });
}
