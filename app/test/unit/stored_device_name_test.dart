import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/devices/stored_device_name.dart';

void main() {
  group('stored device name payload', () {
    test('a name round trips through the version byte', () {
      final payload = encodeStoredDeviceName('Kitchen Omi')!;

      expect(payload.first, storedDeviceNameVersion);
      expect(decodeStoredDeviceName(payload), 'Kitchen Omi');
    });

    test('multi-byte names survive the round trip', () {
      expect(decodeStoredDeviceName(encodeStoredDeviceName('हर्ष का Omi 🎧')!), 'हर्ष का Omi 🎧');
    });

    test('a cleared name is a version byte with nothing after it', () {
      expect(encodeStoredDeviceName('   '), [storedDeviceNameVersion]);
      expect(decodeStoredDeviceName([storedDeviceNameVersion]), '');
    });

    test('an empty read is a failed read, not an empty name', () {
      expect(decodeStoredDeviceName([]), isNull);
    });

    test('an unknown payload version is not trusted', () {
      expect(decodeStoredDeviceName([2, 65, 66]), isNull);
    });

    test('a name longer than the device can store is refused before writing', () {
      expect(encodeStoredDeviceName('a' * maxStoredDeviceNameBytes), hasLength(maxStoredDeviceNameBytes + 1));
      expect(encodeStoredDeviceName('a' * (maxStoredDeviceNameBytes + 1)), isNull);
      expect(encodeStoredDeviceName('🎧' * 33), isNull);
    });
  });
}
