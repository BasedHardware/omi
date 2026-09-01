import 'package:omi/backend/schema/geolocation.dart';

/// Private Dart-to-native handoff contract for live/background BLE streaming.
/// Android and iOS native writers also consume this recording-owned snapshot;
/// native code validates it before forwarding or persisting it.
Map<String, dynamic> buildNativeBleStreamConfig({
  required String deviceId,
  required String codec,
  required int sampleRate,
  required String? source,
  required String apiBaseUrl,
  required String serviceUuid,
  required String characteristicUuid,
  required String deviceType,
  Geolocation? geolocation,
}) {
  return {
    'deviceId': deviceId,
    'codec': codec,
    'sampleRate': sampleRate,
    'source': source,
    'apiBaseUrl': apiBaseUrl,
    'serviceUuid': serviceUuid,
    'characteristicUuid': characteristicUuid,
    'deviceType': deviceType,
    if (geolocation != null) 'geolocation': geolocation.toJson(),
  };
}
