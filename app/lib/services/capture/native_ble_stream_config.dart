import 'package:omi/backend/schema/geolocation.dart';

/// Private Dart-to-Android handoff contract for background BLE streaming.
/// The snapshot is recording-owned and copied once; native code validates and
/// forwards it only on the authenticated `/v4/listen` request.
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
