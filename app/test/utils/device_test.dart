import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/device.dart';

void main() {
  group('DeviceUtils.isOmiDevKit', () {
    test('detects DevKit 2 by model number', () {
      expect(DeviceUtils.isOmiDevKit(modelNumber: 'OMI DEVKIT 2'), isTrue);
    });

    test('detects DevKit by advertised name', () {
      expect(DeviceUtils.isOmiDevKit(deviceName: 'Omi DevKit'), isTrue);
    });

    test('detects the spaced "Dev Kit" spelling (Friend Dev Kit 1)', () {
      expect(DeviceUtils.isOmiDevKit(deviceName: 'Friend Dev Kit 1'), isTrue);
      expect(DeviceUtils.isOmiDevKit(modelNumber: 'Omi Dev Kit 2'), isTrue);
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

    test('Friend Dev Kit 1 (spaced) is NOT CV1 — the forced-onboarding regression', () {
      expect(DeviceUtils.isOmiCv1(deviceName: 'Friend Dev Kit 1'), isFalse);
      expect(DeviceUtils.isOmiCv1(modelNumber: 'Friend Dev Kit 1'), isFalse);
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

    test('a non-variant name alone is enough to treat as CV1', () {
      expect(DeviceUtils.isOmiCv1(deviceName: 'Omi'), isTrue);
    });

    test('concrete CV1 model is authoritative — name cannot veto it', () {
      expect(DeviceUtils.isOmiCv1(modelNumber: 'Omi CV 1', deviceName: 'Omi Neo'), isTrue);
    });

    test('generic fallback model defers to the name (DevKit with failed read)', () {
      expect(DeviceUtils.isOmiCv1(modelNumber: 'Omi Device', deviceName: 'Omi DevKit'), isFalse);
      expect(DeviceUtils.isOmiCv1(modelNumber: 'Unknown', deviceName: 'Omi DevKit'), isFalse);
    });

    test('no identifier at all is NOT positively CV1', () {
      expect(DeviceUtils.isOmiCv1(), isFalse);
      expect(DeviceUtils.isOmiCv1(modelNumber: '', deviceName: ''), isFalse);
      expect(DeviceUtils.isOmiCv1(modelNumber: '   ', deviceName: '  '), isFalse);
    });
  });
}
