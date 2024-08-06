import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/env/env.dart';

Future<void> saveTokenToBackend({
  required String userId,
  required String token,
  required String timeZone,
}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}/save-token',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({
      'user_id': userId,
      'token': token,
      'time_zone': timeZone,
    }),
  );

  debugPrint('saveToken: ${response?.body}');
  if (response?.statusCode == 200) {
    debugPrint("Token saved successfully");
  } else {
    debugPrint("Failed to save token");
  }
}
