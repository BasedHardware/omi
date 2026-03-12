import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

// ************************************************
// *********** PHONE NUMBER MANAGEMENT ************
// ************************************************

Future<Map<String, dynamic>?> verifyPhoneNumber(String phoneNumber) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/phone/numbers/verify',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'phone_number': phoneNumber}),
  );
  if (response == null) return null;
  Logger.debug('verifyPhoneNumber: ${response.body}');
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  }
  try {
    var body = jsonDecode(response.body);
    if (body['detail'] != null) {
      return {'error': body['detail']};
    }
  } catch (_) {}
  return null;
}

Future<Map<String, dynamic>?> checkPhoneVerification(String phoneNumber) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/phone/numbers/verify/check',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'phone_number': phoneNumber}),
  );
  if (response == null) return null;
  Logger.debug('checkPhoneVerification: ${response.body}');
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  }
  return null;
}

Future<List<VerifiedPhoneNumber>> getVerifiedPhoneNumbers() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/phone/numbers',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  if (response.statusCode == 200) {
    var body = jsonDecode(response.body);
    var numbers = body['numbers'] as List<dynamic>;
    return numbers.map((n) => VerifiedPhoneNumber.fromJson(n)).toList();
  }
  return [];
}

Future<bool> deleteVerifiedPhoneNumber(String phoneNumberId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/phone/numbers/$phoneNumberId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  return response?.statusCode == 200;
}

// ************************************************
// ************** TOKEN MANAGEMENT ****************
// ************************************************

Future<PhoneCallToken?> getPhoneCallToken() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/phone/token',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return null;
  Logger.debug('getPhoneCallToken: ${response.body}');
  if (response.statusCode == 200) {
    return PhoneCallToken.fromJson(jsonDecode(response.body));
  }
  return null;
}

// ************************************************
// *********** WEBSOCKET URL BUILDER **************
// ************************************************

String buildPhoneCallWebSocketUrl({
  required String callId,
  required String uid,
  int sampleRate = 48000,
  String codec = 'pcm',
  String language = 'en',
}) {
  var baseUrl = '${Env.apiBaseUrl}'.replaceFirst('https://', 'wss://').replaceFirst('http://', 'ws://');
  return '${baseUrl}v4/listen?source=phone_call&call_id=$callId&uid=$uid&sample_rate=$sampleRate&codec=$codec&language=$language&channels=2';
}
