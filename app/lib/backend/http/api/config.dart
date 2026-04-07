import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

Future<String?> getElevenLabsApiKey() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/config/api-keys',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    try {
      var body = jsonDecode(response.body);
      return body['elevenlabs_api_key'] as String?;
    } catch (e) {
      Logger.debug('Error parsing api-keys response: $e');
      return null;
    }
  }
  return null;
}
