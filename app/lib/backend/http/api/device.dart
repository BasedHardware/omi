import 'dart:convert';

import 'package:crypto/crypto.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/device_speech_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/bootloader_fingerprint.dart';

Uri latestFirmwareVersionUri({
  required String deviceModelNumber,
  required String firmwareRevision,
  required String hardwareRevision,
  required String manufacturerName,
  String? serialNumber,
  String? bootloaderSha256,
}) {
  return Uri.parse('${Env.apiBaseUrl}v2/firmware/latest').replace(queryParameters: {
    'device_model': deviceModelNumber,
    // Measured installed-loader digest from the pendant itself; omitted when unknown.
    if (isBootloaderSha256(bootloaderSha256)) 'bootloader_sha256': bootloaderSha256!,
    'firmware_revision': firmwareRevision,
    'hardware_revision': hardwareRevision,
    'manufacturer_name': manufacturerName,
    // DIS provides the normalized serial. Never put the raw value in request logs.
    if (serialNumber != null && serialNumber.trim().isNotEmpty)
      'device_id': sha256.convert(utf8.encode(serialNumber)).toString(),
  });
}

/// The newest firmware for this device, or null when the request failed (offline, a server error):
/// a failed check is never "up to date" (ux-contract §17.2).
Future<Map?> getLatestFirmwareVersion({
  required String deviceModelNumber,
  required String firmwareRevision,
  required String hardwareRevision,
  required String manufacturerName,
  String? serialNumber,
  String? bootloaderSha256,
}) async {
  var res = await makeApiCall(
    url: latestFirmwareVersionUri(
      deviceModelNumber: deviceModelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
      serialNumber: serialNumber,
      bootloaderSha256: bootloaderSha256,
    ).toString(),
    headers: {},
    body: '',
    method: 'GET',
  );

  if (res == null || res.statusCode != 200) {
    return null;
  }

  return wire.GeneratedFirmwareVersionResponse.fromJson(jsonDecode(res.body) as Map<String, dynamic>).toJson();
}

Uri stableFirmwareVersionUri({required String deviceModelNumber, String? bootloaderSha256}) {
  return Uri.parse('${Env.apiBaseUrl}v2/firmware/stable').replace(queryParameters: {
    'device_model': deviceModelNumber,
    if (isBootloaderSha256(bootloaderSha256)) 'bootloader_sha256': bootloaderSha256!,
  });
}

/// The stable firmware for this model, or null when the request failed.
Future<Map?> getStableFirmwareVersion({required String deviceModelNumber, String? bootloaderSha256}) async {
  var res = await makeApiCall(
    url: stableFirmwareVersionUri(deviceModelNumber: deviceModelNumber, bootloaderSha256: bootloaderSha256).toString(),
    headers: {},
    body: '',
    method: 'GET',
  );

  if (res == null || res.statusCode != 200) {
    return null;
  }

  return wire.GeneratedFirmwareVersionResponse.fromJson(jsonDecode(res.body) as Map<String, dynamic>).toJson();
}
