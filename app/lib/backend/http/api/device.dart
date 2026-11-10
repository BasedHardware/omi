import 'dart:convert';

import 'package:crypto/crypto.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/device_speech_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

Uri latestFirmwareVersionUri({
  required String deviceModelNumber,
  required String firmwareRevision,
  required String hardwareRevision,
  required String manufacturerName,
  String? serialNumber,
}) {
  return Uri.parse('${Env.apiBaseUrl}v2/firmware/latest').replace(queryParameters: {
    'device_model': deviceModelNumber,
    'firmware_revision': firmwareRevision,
    'hardware_revision': hardwareRevision,
    'manufacturer_name': manufacturerName,
    // DIS provides the normalized serial. Never put the raw value in request logs.
    if (serialNumber != null && serialNumber.trim().isNotEmpty)
      'device_id': sha256.convert(utf8.encode(serialNumber)).toString(),
  });
}

Future<Map> getLatestFirmwareVersion({
  required String deviceModelNumber,
  required String firmwareRevision,
  required String hardwareRevision,
  required String manufacturerName,
  String? serialNumber,
}) async {
  var res = await makeApiCall(
    url: latestFirmwareVersionUri(
      deviceModelNumber: deviceModelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
      serialNumber: serialNumber,
    ).toString(),
    headers: {},
    body: '',
    method: 'GET',
  );

  if (res == null || res.statusCode != 200) {
    return {};
  }

  return wire.GeneratedFirmwareVersionResponse.fromJson(jsonDecode(res.body) as Map<String, dynamic>).toJson();
}

Future<Map> getStableFirmwareVersion({required String deviceModelNumber}) async {
  var res = await makeApiCall(
    url: "${Env.apiBaseUrl}v2/firmware/stable?device_model=$deviceModelNumber",
    headers: {},
    body: '',
    method: 'GET',
  );

  if (res == null || res.statusCode != 200) {
    return {};
  }

  return wire.GeneratedFirmwareVersionResponse.fromJson(jsonDecode(res.body) as Map<String, dynamic>).toJson();
}
