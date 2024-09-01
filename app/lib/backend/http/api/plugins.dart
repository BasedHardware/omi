import 'dart:convert';
import 'dart:developer';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

Future<List<Plugin>> retrievePlugins() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/plugins',
    headers: {},
    body: '',
    method: 'GET',
  );
  if (response?.statusCode == 200) {
    try {
      log('plugins: ${response?.body}');
      var plugins = Plugin.fromJsonList(jsonDecode(response!.body));
      plugins = plugins.where((p) => !p.deleted).toList();
      SharedPreferencesUtil().pluginsList = plugins;
      return plugins;
    } catch (e, stackTrace) {
      debugPrint(e.toString());
      CrashReporting.reportHandledCrash(e, stackTrace);
      return SharedPreferencesUtil().pluginsList;
    }
  }
  return SharedPreferencesUtil().pluginsList;
}

Future<bool> enablePluginServer(String pluginId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugins/enable?plugin_id=$pluginId',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  debugPrint('enablePluginServer: $pluginId ${response.body}');
  return response.statusCode == 200;
}

Future<bool> disablePluginServer(String pluginId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugins/disable?plugin_id=$pluginId',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  debugPrint('disablePluginServer: ${response.body}');
  return response.statusCode == 200;
}

Future<void> reviewPlugin(String pluginId, double score, {String review = ''}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugins/review?plugin_id=$pluginId',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'score': score, review: review}),
  );
  debugPrint('reviewPlugin: ${response?.body}');
}

Future<void> migrateUserServer(String prevUid, String newUid) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}migrate-user?prev_uid=$prevUid&new_uid=$newUid',
    headers: {},
    method: 'POST',
    body: '',
  );
  debugPrint('migrateUser: ${response?.body}');
}

Future<String> getPluginMarkdown(String pluginMarkdownPath) async {
  // https://raw.githubusercontent.com/BasedHardware/Friend/main/assets/external_plugins_instructions/notion-conversations-crm.md
  var response = await makeApiCall(
    url: 'https://raw.githubusercontent.com/BasedHardware/Friend/main$pluginMarkdownPath',
    method: 'GET',
    headers: {},
    body: '',
  );
  return response?.body ?? '';
}

Future<bool> isPluginSetupCompleted(String? url) async {
  if (url == null || url.isEmpty) return true;
  print('isPluginSetupCompleted: $url');
  var response = await makeApiCall(
    url: '$url?uid=${SharedPreferencesUtil().uid}',
    method: 'GET',
    headers: {},
    body: '',
  );
  var data = jsonDecode(response?.body ?? '{}');
  print(data);
  return data['is_setup_completed'] ?? false;
}
