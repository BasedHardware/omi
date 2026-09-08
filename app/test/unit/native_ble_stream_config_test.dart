import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/capture/native_ble_stream_config.dart';

void main() {
  test('native BLE handoff config includes the canonical start snapshot and provenance', () {
    final config = buildNativeBleStreamConfig(
      deviceId: 'device-1',
      codec: 'opus',
      sampleRate: 16000,
      source: 'omi',
      apiBaseUrl: 'https://api.omiapi.com/',
      serviceUuid: 'service',
      characteristicUuid: 'characteristic',
      deviceType: 'omi',
      geolocation: Geolocation(
        latitude: 37.7749,
        longitude: -122.4194,
        accuracy: 8,
        time: DateTime.utc(2026, 8, 1, 12, 30),
        captureSource: 'current_position',
      ),
    );

    expect(config['geolocation'], {
      'latitude': 37.7749,
      'longitude': -122.4194,
      'id': 0,
      'altitude': null,
      'accuracy': 8.0,
      'captured_at': '2026-08-01T12:30:00.000Z',
      'capture_source': 'current_position',
      'google_place_id': null,
      'location_type': null,
      'address': null,
    });
  });

  test('native BLE handoff config omits location when capture failed soft', () {
    final config = buildNativeBleStreamConfig(
      deviceId: 'device-1',
      codec: 'opus',
      sampleRate: 16000,
      source: 'omi',
      apiBaseUrl: 'https://api.omiapi.com/',
      serviceUuid: 'service',
      characteristicUuid: 'characteristic',
      deviceType: 'omi',
    );

    expect(config, isNot(contains('geolocation')));
  });
}
