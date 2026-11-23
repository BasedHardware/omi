import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/misc_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/services/notifications/fcm_token_registration.dart';

Future<void> syncUserTimeZoneServer({required String timeZone}) async {
  await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/time-zone',
    headers: {},
    method: 'PUT',
    body: jsonEncode({'time_zone': timeZone}),
  );
}

Future<bool> saveFcmTokenServer({
  required String token,
  required String timeZone,
  required bool Function() canLogDiagnostic,
  bool Function()? canSend,
  Future<http.Response?> Function({
    required String url,
    required Map<String, String> headers,
    required String method,
    required String body,
    bool Function()? canSend,
    bool signOutOn401,
  }) send = makeApiCall,
}) async {
  void record(PushRegistrationStage stage, PushRegistrationResult result, {int? httpStatus}) {
    if (canLogDiagnostic()) {
      unawaited(logPushRegistration(stage, result, httpStatus: httpStatus));
    }
  }

  final int? order;
  try {
    order = await reserveFcmRegistrationOrder();
  } catch (_) {
    record(PushRegistrationStage.localOrder, PushRegistrationResult.exception);
    rethrow;
  }
  if (order == null) {
    record(PushRegistrationStage.localOrder, PushRegistrationResult.declined);
    return false;
  }
  final response = await send(
    url: '${Env.apiBaseUrl}v1/users/fcm-token',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'fcm_token': token, 'time_zone': timeZone, 'registration_order': order}),
    canSend: canSend,
    signOutOn401: false,
  );

  if (response?.statusCode == 200) {
    final bool accepted;
    try {
      final data = wire.GeneratedFcmTokenResponse.fromJson(jsonDecode(response!.body) as Map<String, dynamic>);
      accepted = data.status == 'Ok';
    } catch (_) {
      record(PushRegistrationStage.http, PushRegistrationResult.invalidResponse, httpStatus: 200);
      rethrow;
    }
    record(
      PushRegistrationStage.http,
      accepted ? PushRegistrationResult.accepted : PushRegistrationResult.invalidResponse,
      httpStatus: 200,
    );
    return accepted;
  }
  record(
    PushRegistrationStage.http,
    response == null ? PushRegistrationResult.unavailable : PushRegistrationResult.declined,
    httpStatus: response?.statusCode,
  );
  return false;
}
