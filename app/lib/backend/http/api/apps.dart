import 'dart:convert';
import 'dart:developer';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

import 'package:http/http.dart' as http;
import 'package:path/path.dart';

Future<List<App>> retrieveApps() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps',
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
    url: '${Env.apiBaseUrl}v1/apps/enable?app_id=$appId',
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
    url: '${Env.apiBaseUrl}v1/apps/disable?app_id=$appId',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  debugPrint('disableAppServer: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> reviewApp(String appId, AppReview review) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/apps/review?app_id=$appId',
      headers: {'Content-Type': 'application/json'},
      method: 'POST',
      body: jsonEncode(review.toJson()),
    );
    debugPrint('reviewApp: ${response?.body}');
    return response?.statusCode == 200;
  } catch (e) {
    debugPrint('Error reviewing app: $e');
    return false;
  }
}

Future<bool> updateAppReview(String appId, AppReview review) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/apps/$appId/review',
      headers: {'Content-Type': 'application/json'},
      method: 'PATCH',
      body: jsonEncode(review.toJson()),
    );
    debugPrint('updateAppReview: ${response?.body}');
    return response?.statusCode == 200;
  } catch (e) {
    debugPrint('Error updating app review: $e');
    return false;
  }
}

Future<bool> replyToAppReview(String appId, String reply) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/apps/$appId/review/reply',
      headers: {'Content-Type': 'application/json'},
      method: 'PATCH',
      body: jsonEncode({'response': reply}),
    );
    debugPrint('replyToAppReview: ${response?.body}');
    return response?.statusCode == 200;
  } catch (e) {
    debugPrint('Error replying to app review: $e');
    return false;
  }
}

Future<List<AppReview>> getAppReviews(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/$appId/reviews',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return [];
    log('getAppReviews: ${response.body}');
    return AppReview.fromJsonList(jsonDecode(response.body));
  } catch (e) {
    debugPrint(e.toString());
    return [];
  }
}

Future<String> getAppMarkdown(String appMarkdownPath) async {
  var response = await makeApiCall(
    url: appMarkdownPath,
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

Future<List<AppUsageHistory>> retrieveAppUsageHistory(String pluginId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugins/$pluginId/usage',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return [];
    log('retrieveAppUsageHistory: ${response.body}');
    return AppUsageHistory.fromJsonList(jsonDecode(response.body));
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    CrashReporting.reportHandledCrash(e, stackTrace);
    return [];
  }
}

Future<double> getAppMoneyMade(String pluginId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugins/$pluginId/money',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return 0;
    log('retrieveAppUsageHistory: ${response.body}');
    return jsonDecode(response.body)['money'];
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    CrashReporting.reportHandledCrash(e, stackTrace);
    return 0;
  }
}

Future<bool> submitAppServer(File file, Map<String, dynamic> appData) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}v1/apps'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));
  request.headers.addAll({'Authorization': await getAuthHeader()});
  request.fields.addAll({'app_data': jsonEncode(appData)});
  print(jsonEncode(appData));
  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      debugPrint('submitAppServer Response body: ${jsonDecode(response.body)}');
      return true;
    } else {
      debugPrint('Failed to submit app. Status code: ${response.statusCode}');
      return false;
    }
  } catch (e) {
    debugPrint('An error occurred submitAppServer: $e');
    return false;
  }
}

Future<bool> updateAppServer(File? file, Map<String, dynamic> appData) async {
  var request = http.MultipartRequest(
    'PATCH',
    Uri.parse('${Env.apiBaseUrl}v1/apps/${appData['id']}'),
  );
  if (file != null) {
    request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));
  }
  request.headers.addAll({'Authorization': await getAuthHeader()});
  request.fields.addAll({'app_data': jsonEncode(appData)});
  print(jsonEncode(appData));
  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      debugPrint('updateAppServer Response body: ${jsonDecode(response.body)}');
      return true;
    } else {
      debugPrint('Failed to update app. Status code: ${response.statusCode}');
      return false;
    }
  } catch (e) {
    debugPrint('An error occurred updateAppServer: $e');
    return false;
  }
}

Future<List<Category>> getAppCategories() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugin-categories',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return [];
    log('getAppCategories: ${response.body}');
    var res = jsonDecode(response.body);
    return Category.fromJsonList(res);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    CrashReporting.reportHandledCrash(e, stackTrace);
    return [];
  }
}

Future<List<AppCapability>> getAppCapabilitiesServer() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/app-capabilities',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return [];
    log('getAppCapabilities: ${response.body}');
    var res = jsonDecode(response.body);
    return AppCapability.fromJsonList(res);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    CrashReporting.reportHandledCrash(e, stackTrace);
    return [];
  }
}

Future<List<TriggerEvent>> getTriggerEventsServer() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugin-triggers',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return [];
    log('getTriggerEvents: ${response.body}');
    var res = jsonDecode(response.body);
    return TriggerEvent.fromJsonList(res);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    CrashReporting.reportHandledCrash(e, stackTrace);
    return [];
  }
}

Future<List<NotificationScope>> getNotificationScopesServer() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/proactive-notification-scopes',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return [];
    log('getNotificationScopes: ${response.body}');
    var res = jsonDecode(response.body);
    return NotificationScope.fromJsonList(res);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    CrashReporting.reportHandledCrash(e, stackTrace);
    return [];
  }
}

Future changeAppVisibilityServer(String appId, bool makePublic) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/$appId/change-visibility?private=${!makePublic}',
    headers: {},
    body: '',
    method: 'PATCH',
  );
  try {
    if (response == null || response.statusCode != 200) return false;
    log('changeAppVisibilityServer: ${response.body}');
    return true;
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    CrashReporting.reportHandledCrash(e, stackTrace);
    return false;
  }
}

Future deleteAppServer(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/$appId',
    headers: {},
    body: '',
    method: 'DELETE',
  );
  try {
    if (response == null || response.statusCode != 200) return false;
    log('deleteAppServer: ${response.body}');
    return true;
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    CrashReporting.reportHandledCrash(e, stackTrace);
    return false;
  }
}

Future<Map<String, dynamic>?> getAppDetailsServer(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/$appId',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return null;
    log('getAppDetailsServer: ${response.body}');
    return jsonDecode(response.body);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    CrashReporting.reportHandledCrash(e, stackTrace);
    return null;
  }
}
