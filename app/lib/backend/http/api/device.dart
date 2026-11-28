import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/device_speech_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/bootloader_fingerprint.dart';
import 'package:omi/utils/device.dart';

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

/// The newest firmware for this device, or null when the request failed (offline, a server error): a failed
/// check is never "up to date" (ux-contract §17.2). With [noNewerAsUpToDate] (the CV1 firmware page only),
/// the server's "nothing newer" answer is [DeviceUtils.firmwareUpToDate] instead of null.
Future<Map?> getLatestFirmwareVersion({
  required String deviceModelNumber,
  required String firmwareRevision,
  required String hardwareRevision,
  required String manufacturerName,
  String? serialNumber,
  String? bootloaderSha256,
  bool noNewerAsUpToDate = false,
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

  return latestFirmwareAnswer(res, noNewerAsUpToDate: noNewerAsUpToDate);
}

/// The 404 detail every released backend sends when no newer release exists for the device
/// (contracts/client-compat). Other 404s (unknown device, no releases) are failed checks.
const _noNewerFirmwareDetail = 'No suitable firmware update found for your device version.';

/// Reads a `/v2/firmware/latest` response: the release, [DeviceUtils.firmwareUpToDate] (only with
/// [noNewerAsUpToDate]), or null. The connection check and OpenGlass OTA read every non-200 as null.
Map? latestFirmwareAnswer(http.Response? res, {bool noNewerAsUpToDate = false}) {
  if (res == null) return null;
  if (noNewerAsUpToDate && res.statusCode == 404 && _errorDetail(res.body) == _noNewerFirmwareDetail) {
    return DeviceUtils.firmwareUpToDate;
  }
  if (res.statusCode != 200) return null;

  return wire.GeneratedFirmwareVersionResponse.fromJson(jsonDecode(res.body) as Map<String, dynamic>).toJson();
}

String? _errorDetail(String body) {
  try {
    final json = jsonDecode(body);
    final detail = json is Map ? json['detail'] : null;
    return detail is String ? detail : null;
  } on FormatException {
    return null;
  }
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
