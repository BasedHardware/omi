import 'dart:convert';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

Future<Map> getLatestFirmwareVersion({
  required String deviceModelNumber,
  required String firmwareRevision,
  required String hardwareRevision,
  required String manufacturerName,
}) async {
  var res = await makeApiCall(
      url:
          "${Env.apiBaseUrl}v2/firmware/latest?device_model=$deviceModelNumber&firmware_revision=$firmwareRevision&hardware_revision=$hardwareRevision&manufacturer_name=$manufacturerName",
      headers: {},
      body: '',
      method: 'GET');

  if (res == null || res.statusCode != 200) {
    return {};
  }

  return jsonDecode(res.body);
}
