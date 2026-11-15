import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/misc_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/services/notifications/fcm_token_registration.dart' show reserveFcmRegistrationOrder;
import 'package:omi/utils/logger.dart';

Future<void> syncUserTimeZoneServer({required String timeZone}) async {
  await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/time-zone',
    headers: {},
    method: 'PUT',
    body: jsonEncode({'time_zone': timeZone}),
  );
}

Future<bool> saveFcmTokenServer({required String token, required String timeZone, bool Function()? canSend}) async {
  final order = await reserveFcmRegistrationOrder();
  if (order == null) return false;
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/fcm-token',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'fcm_token': token, 'time_zone': timeZone, 'registration_order': order}),
    canSend: canSend,
    signOutOn401: false,
  );

  if (response?.statusCode == 200) {
    final data = wire.GeneratedFcmTokenResponse.fromJson(jsonDecode(response!.body) as Map<String, dynamic>);
    return data.status == 'Ok';
  }
  Logger.debug('Push token persistence deferred (status=${response?.statusCode})');
  return false;
}
