import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/env/env.dart';

Future<void> saveFcmTokenServer({
  required String token,
  required String timeZone,
}) async {
  // Log the request details
  print('saveFcmTokenServer Request URL: ${Env.apiBaseUrl}v1/users/fcm-token');
  print('saveFcmTokenServer Request Method: POST');
  print('saveFcmTokenServer Request Headers: ${jsonEncode({'Content-Type': 'application/json'})}');
  print('saveFcmTokenServer Request Body: ${jsonEncode({'fcm_token': token, 'time_zone': timeZone})}');

  // Make the API call
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/fcm-token',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'fcm_token': token, 'time_zone': timeZone}),
  );

  // Log the response details
  print('saveFcmTokenServer Response Status Code: ${response?.statusCode}');
  print('saveFcmTokenServer Response Body: ${response?.body}');

  // Handle the response
  if (response == null) {
    print('saveFcmTokenServer: No response received');
  } else if (response.statusCode == 200) {
    print('saveFcmTokenServer: Token saved successfully');
  } else {
    print('saveFcmTokenServer: Failed to save token');
  }
}