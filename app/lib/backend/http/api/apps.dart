import 'dart:convert';
import 'dart:developer';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

Future<List<App>> retrieveApps() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/plugins',
    headers: {},
    body: '',
    method: 'GET',
  );
  if (response != null && response.statusCode == 200 && response.body.isNotEmpty) {
    try {
      log('apps: ${response.body}');
      var apps = App.fromJsonList(jsonDecode(response.body));
      apps = apps.where((p) => !p.deleted).toList();
      SharedPreferencesUtil().appsList = apps;
      return apps;
    } catch (e, stackTrace) {
      debugPrint(e.toString());
      CrashReporting.reportHandledCrash(e, stackTrace);
      return SharedPreferencesUtil().appsList;
    }
  }
  return SharedPreferencesUtil().appsList;
}

Future<bool> enableAppServer(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugins/enable?plugin_id=$appId',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  debugPrint('enableAppServer: $appId ${response.body}');
  return response.statusCode == 200;
}

Future<bool> disableAppServer(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugins/disable?plugin_id=$appId',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  debugPrint('disableAppServer: ${response.body}');
  return response.statusCode == 200;
}

Future<void> reviewApp(String appId, double score, {String review = ''}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugins/review?plugin_id=$appId',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'score': score, review: review}),
  );
  debugPrint('reviewApp: ${response?.body}');
}

Future<String> getAppMarkdown(String appMarkdownPath) async {
  var response = await makeApiCall(
    url: 'https://raw.githubusercontent.com/BasedHardware/Omi/main$appMarkdownPath',
    method: 'GET',
    headers: {},
    body: '',
  );
  return response?.body ?? '';
}

Future<bool> isAppSetupCompleted(String? url) async {
  if (url == null || url.isEmpty) return true;
  print('isAppSetupCompleted: $url');
  var response = await makeApiCall(
    url: '$url?uid=${SharedPreferencesUtil().uid}',
    method: 'GET',
    headers: {},
    body: '',
  );
  var data;
  try {
    data = jsonDecode(response?.body ?? '{}');
    print(data);
    return data['is_setup_completed'] ?? false;
  } on FormatException catch (e) {
    debugPrint('Response not a valid json: $e');
    return false;
  } catch (e) {
    debugPrint('Error triggering memory request at endpoint: $e');
    return false;
  }
}
