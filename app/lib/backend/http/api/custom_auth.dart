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

_setFieldsFromBody(Map<String, dynamic> body) {
  SharedPreferencesUtil().authToken = body['token'] ?? '';
  SharedPreferencesUtil().tokenExpirationTime = body['exp'] != null ? body['exp'] * 1000 : 0;
  SharedPreferencesUtil().uid = body['uid'] ?? '';

  String name = body['name'] ?? '';
  List<String> nameParts = name.split(' ');

  SharedPreferencesUtil().givenName = nameParts.isNotEmpty ? nameParts[0] : '';
  SharedPreferencesUtil().familyName = nameParts.length > 1 ? nameParts.sublist(1).join(' ') : '';
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
      _setFieldsFromBody(body);
      SharedPreferencesUtil().email = email;
      SharedPreferencesUtil().customAuthPassword = password;
      return true;
    } catch (e, stackTrace) {
      debugPrint(e.toString());
      _setFieldsFromBody({});
      SharedPreferencesUtil().email = '';
      SharedPreferencesUtil().customAuthPassword = '';
      CrashReporting.reportHandledCrash(e, stackTrace);
      return false;
    }
  }
  _setFieldsFromBody({});
  SharedPreferencesUtil().email = '';
  SharedPreferencesUtil().customAuthPassword = '';
  return false;
}

// TODO:
// 1. Check every navigation works as expected. (without customBackend)
// 2. When backend url set, should return to login screen, and setState refreshed, to not show the apple/google login
// 3. Sign up completed, goes back to login screen, snackbar please sign in
// 4. sign in completed, goes back to login screen widget.onSignIn is called
// 5. skip name onboarding widget (on auth completion, but also on wrapper widget loaded)
// 6. everything should work now
// 7. test with custom backend url
// 8. modify sign out to clear email/pwd instead.
// 9. Option to clear backend url widget data, remove it.
// 10. On settings it should be shown that the app is using custom backend URL