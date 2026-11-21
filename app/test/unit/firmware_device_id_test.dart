import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/device.dart';
import 'package:omi/env/env.dart';

Uri _latestUri({String? serial}) => latestFirmwareVersionUri(
      deviceModelNumber: 'Omi CV 1',
      firmwareRevision: '3.0.21',
      hardwareRevision: '5.0',
      manufacturerName: 'Based Hardware',
      serialNumber: serial,
    );

void main() {
  setUp(() => Env.overrideApiBaseUrl('https://firmware.test.invalid/'));
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  test('latest firmware query sends the serial SHA-256 hex digest, never the raw serial', () {
    const serial = '1A2B3C4D5E6F7081';
    final uri = _latestUri(serial: serial);

    expect(uri.path, endsWith('/v2/firmware/latest'));
    expect(uri.queryParameters, {
      'device_model': 'Omi CV 1',
      'firmware_revision': '3.0.21',
      'hardware_revision': '5.0',
      'manufacturer_name': 'Based Hardware',
      'device_id': '251b333538ab7f5b63b8734c80793fca98bfb098d0bd174f58bdb3271be83a18',
    });
    expect(uri.toString(), isNot(contains(serial)));
    expect(_latestUri(serial: serial), uri);
    expect(
        _latestUri(serial: '2A2B3C4D5E6F7081').queryParameters['device_id'], isNot(uri.queryParameters['device_id']));
  });

  for (final serial in [null, '', '   ']) {
    test('latest firmware query omits device_id when serial is ${serial == null ? 'null' : 'blank ($serial)'}', () {
      final uri = _latestUri(serial: serial);

      expect(uri.queryParameters.containsKey('device_id'), isFalse);
      expect(
          uri.queryParameters.keys,
          unorderedEquals([
            'device_model',
            'firmware_revision',
            'hardware_revision',
            'manufacturer_name',
          ]));
      expect(uri.toString(), isNot(contains('device_id')));
    });
  }
}
