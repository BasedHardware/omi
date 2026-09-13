/// Client-side mirror of the firmware device-name rules
/// (omi/firmware/omi/src/lib/core/device_name.h). Keeps the app from sending
/// a name the pendant would reject and from trusting a payload it could not
/// have produced.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/devices/device_name_policy.dart';

void main() {
  group('OmiDeviceNamePolicy.validate', () {
    test('accepts plain and unicode names inside the byte budget', () {
      expect(OmiDeviceNamePolicy.validate('Omi'), isNull);
      expect(OmiDeviceNamePolicy.validate("Ana's Omi"), isNull);
      expect(OmiDeviceNamePolicy.validate('Léo'), isNull);
      expect(OmiDeviceNamePolicy.validate('Omi 🎧'), isNull);
      expect(OmiDeviceNamePolicy.validate('12345678901234567890'), isNull); // exactly 20 bytes
    });

    test('rejects empty names', () {
      expect(OmiDeviceNamePolicy.validate(''), DeviceNameError.empty);
    });

    test('limit is UTF-8 bytes, not characters', () {
      expect(OmiDeviceNamePolicy.validate('123456789012345678901'), DeviceNameError.tooLong);
      // 20 characters but 21 bytes.
      expect(OmiDeviceNamePolicy.validate('1234567890123456789é'), DeviceNameError.tooLong);
      // 5 emoji = 20 bytes.
      expect(OmiDeviceNamePolicy.validate('🎧🎧🎧🎧🎧'), isNull);
      expect(OmiDeviceNamePolicy.validate('🎧🎧🎧🎧🎧a'), DeviceNameError.tooLong);
    });

    test('rejects control characters and unpaired surrogates', () {
      expect(OmiDeviceNamePolicy.validate('Omi\n'), DeviceNameError.invalidCharacters);
      expect(OmiDeviceNamePolicy.validate('Om\ti'), DeviceNameError.invalidCharacters);
      expect(OmiDeviceNamePolicy.validate('Omi\x7F'), DeviceNameError.invalidCharacters);
      expect(OmiDeviceNamePolicy.validate('Omi\uD83C'), DeviceNameError.invalidCharacters);
    });
  });

  test('normalize trims the surrounding whitespace the firmware rejects', () {
    expect(OmiDeviceNamePolicy.normalize('  My Omi \n'), 'My Omi');
  });

  group('encode / decode', () {
    test('round-trips UTF-8', () {
      final bytes = OmiDeviceNamePolicy.encode('Léo 🎧');
      expect(bytes.length, 9);
      expect(OmiDeviceNamePolicy.decode(bytes), 'Léo 🎧');
    });

    test('encode refuses invalid names instead of sending them', () {
      expect(() => OmiDeviceNamePolicy.encode(''), throwsArgumentError);
      expect(() => OmiDeviceNamePolicy.encode('x' * 21), throwsArgumentError);
    });

    test('decode returns null for empty or malformed payloads', () {
      expect(OmiDeviceNamePolicy.decode([]), isNull);
      expect(OmiDeviceNamePolicy.decode([0xC3]), isNull);
      expect(OmiDeviceNamePolicy.decode([0x4F, 0x6D, 0x69, 0x00]), isNull);
    });
  });
}
