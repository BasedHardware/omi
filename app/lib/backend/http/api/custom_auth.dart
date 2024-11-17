import 'dart:convert';
import 'dart:developer';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

Future<bool> customAuthSignUp(String name, String email, String password) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/signup',
    headers: {},
    body: jsonEncode({'name': name, 'email': email, 'password': password}),
    method: 'GET',
  );
  if (response != null && response.statusCode == 200 && response.body.isNotEmpty) {
    try {
      log('customAuth signUp: ${response.body}');
      return true;
    } catch (e, stackTrace) {
      debugPrint(e.toString());
      CrashReporting.reportHandledCrash(e, stackTrace);
      return false;
    }
  }
  return false;
}

Future<bool> customAuthSignIn(String email, String password) async {
  if (email.isEmpty || password.isEmpty) {
    return false;
  }
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/signin',
    headers: {},
    body: jsonEncode({'email': email, 'password': password}),
    method: 'GET',
  );
  if (response != null && response.statusCode == 200 && response.body.isNotEmpty) {
    try {
      log('customAuth signIn: ${response.body}');
      var body = jsonDecode(response.body);
      SharedPreferencesUtil().authToken = body['token'];
      SharedPreferencesUtil().tokenExpirationTime = body['exp'] * 1000;
      SharedPreferencesUtil().uid = body['uid'];
      String name = body['name'] ?? '';
      List<String> nameParts = name.split(' ');
      SharedPreferencesUtil().givenName = nameParts[0];
      SharedPreferencesUtil().familyName = nameParts.length > 1 ? nameParts[1] : '';
      SharedPreferencesUtil().email = email;
      SharedPreferencesUtil().customAuthPassword = password;

      // TODO: modify also authProvider, to disable any logic there
      // TODO: http requests when getting the token, should use this token.
      // TODO: on main.dart every time the app is opened
      return true;
    } catch (e, stackTrace) {
      debugPrint(e.toString());
      CrashReporting.reportHandledCrash(e, stackTrace);
      return false;
    }
  }
  return false;
}
