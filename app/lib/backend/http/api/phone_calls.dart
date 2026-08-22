import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/misc_wire.g.dart' as misc_wire;
import 'package:omi/backend/schema/gen/phone_calls_wire.g.dart' as wire;
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

// ************************************************
// ************** ERROR REPORTING *****************
// ************************************************

/// Human-readable reason out of a FastAPI error body, or null when the body
/// carries none.
///
/// ``detail`` is deliberately untyped on the wire: most phone-call endpoints
/// answer with a plain string, but the quota error answers with a map (see
/// ``check_call_access`` in ``backend/utils/phone_calls.py``). Reading it as a
/// string crashes on that map, so both shapes are handled here once.
String? errorDetailMessage(String body) {
  try {
    final parsed = misc_wire.GeneratedErrorResponse.fromJson(jsonDecode(body) as Map<String, dynamic>);
    final detail = parsed.detail;
    if (detail is String) {
      return detail.trim().isEmpty ? null : detail;
    }
    if (detail is Map) {
      final code = detail['error'];
      if (code == 'phone_call_quota_exceeded') {
        final limit = detail['monthly_limit'];
        return limit is int
            ? 'Monthly call limit reached ($limit calls). It resets at the start of next month.'
            : 'Monthly call limit reached. It resets at the start of next month.';
      }
      if (code is String && code.trim().isNotEmpty) {
        return code;
      }
    }
  } catch (_) {}
  return null;
}

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
    final generated = wire.GeneratedVerifyPhoneNumberResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    return generated.toJson();
  }
  final detail = errorDetailMessage(response.body);
  if (detail != null) {
    return {'error': detail};
  }
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
    final generated = wire.GeneratedCheckVerificationResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    return generated.toJson();
  }
  return null;
}

Future<List<VerifiedPhoneNumber>> getVerifiedPhoneNumbers() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/phone/numbers', headers: {}, method: 'GET', body: '');
  if (response == null) return [];
  if (response.statusCode == 200) {
    final generated = wire.GeneratedPhoneNumbersResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return generated.numbers.toList();
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

/// A call token, or the reason the backend refused to mint one.
class PhoneCallTokenResult {
  final PhoneCallToken? token;
  final String? error;

  const PhoneCallTokenResult({this.token, this.error});
}

Future<PhoneCallTokenResult> getPhoneCallToken() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/phone/token', headers: {}, method: 'POST', body: '');
  if (response == null) return const PhoneCallTokenResult();
  Logger.debug('getPhoneCallToken: ${response.body}');
  if (response.statusCode == 200) {
    final generated = wire.GeneratedTokenResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return PhoneCallTokenResult(token: PhoneCallToken.fromGenerated(generated));
  }
  return PhoneCallTokenResult(error: errorDetailMessage(response.body));
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
