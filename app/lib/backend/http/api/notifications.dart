import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

Future<void> saveFcmTokenServer({required String token, required String timeZone}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/fcm-token',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'fcm_token': token, 'time_zone': timeZone}),
  );

  debugPrint('saveToken: ${response?.body}');
  if (response?.statusCode == 200) {
    debugPrint("Token saved successfully");
  } else {
    debugPrint("Failed to save token");
  }
}
