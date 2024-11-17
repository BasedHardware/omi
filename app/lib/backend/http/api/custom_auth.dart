import 'dart:convert';
import 'dart:developer';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

Future<bool> signIn(String name, String email, String password) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/signin',
    headers: {},
    body: jsonEncode({'name': name, 'email': email, 'password': password}),
    method: 'GET',
  );
  if (response != null && response.statusCode == 200 && response.body.isNotEmpty) {
    try {
      log('apps: ${response.body}');
      var body = jsonDecode(response.body);
      // SharedPreferencesUtil().token = body['token'];
      // SharedPreferencesUtil().uid = body['uid'];
      // SharedPreferencesUtil().expiresAt = body['expiresAt'];
      // SharedPreferencesUtil().givenName = body['name']?.split(' ')[0] ?? '';
      // SharedPreferencesUtil().password = password;
      SharedPreferencesUtil().email = email;

      // TODO: modify also authProvider, to disable any logic there
      // TODO: http requests when getting the token, should use this token.
      // TODO: on main.dart every time the app is opened
    } catch (e, stackTrace) {
      debugPrint(e.toString());
      CrashReporting.reportHandledCrash(e, stackTrace);
      return false;
    }
  }
  return false;
}
