import 'dart:convert';
import 'dart:developer';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/env/env.dart';

import 'package:http/http.dart' as http;
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
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
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
      return SharedPreferencesUtil().appsList;
    }
  }
  return SharedPreferencesUtil().appsList;
}

Future<List<App>> retrievePopularApps() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/popular',
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
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
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

Future<Map<String, String>> uploadAppThumbnail(File file) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}v1/app/thumbnails'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));
  request.headers.addAll({'Authorization': await getAuthHeader()});

  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      var data = jsonDecode(response.body);
      return {
        'thumbnail_url': data['thumbnail_url'],
        'thumbnail_id': data['thumbnail_id'],
      };
    } else {
      debugPrint('Failed to upload thumbnail. Status code: ${response.statusCode}');
      return {};
    }
  } catch (e) {
    debugPrint('An error occurred uploading thumbnail: $e');
    return {};
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

Future<bool> replyToAppReview(String appId, String reply, String reviewerUid) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/apps/$appId/review/reply',
      headers: {'Content-Type': 'application/json'},
      method: 'PATCH',
      body: jsonEncode({'response': reply, 'reviewer_uid': reviewerUid}),
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
  Logger.debug('isAppSetupCompleted: $url');
  var response = await makeApiCall(
    url: '$url?uid=${SharedPreferencesUtil().uid}',
    method: 'GET',
    headers: {},
    body: '',
  );
  var data;
  try {
    data = jsonDecode(response?.body ?? '{}');
    Logger.debug(data);
    return data['is_setup_completed'] ?? false;
  } on FormatException catch (e) {
    debugPrint('Response not a valid json: $e');
    return false;
  } catch (e) {
    debugPrint('Error triggering request at endpoint: $e');
    return false;
  }
}

Future<(bool, String, String?)> submitAppServer(File file, Map<String, dynamic> appData) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}v1/apps'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));
  request.headers.addAll({'Authorization': await getAuthHeader()});
  request.fields.addAll({'app_data': jsonEncode(appData)});
  debugPrint(jsonEncode(appData));
  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      var respData = jsonDecode(response.body);
      String? appId = respData['app_id'];
      debugPrint('submitAppServer Response body: $respData');
      return (true, '', appId);
    } else {
      debugPrint('Failed to submit app. Status code: ${response.statusCode}');
      if (response.body.isNotEmpty) {
        return (
          false,
          jsonDecode(response.body)['detail'] as String,
          null,
        );
      } else {
        return (false, 'Failed to submit app. Please try again later', '');
      }
    }
  } catch (e) {
    debugPrint('An error occurred submitAppServer: $e');
    return (false, 'Failed to submit app. Please try again later', null);
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
  debugPrint(jsonEncode(appData));
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
    url: '${Env.apiBaseUrl}v1/app-categories',
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
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
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
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
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
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
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
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
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
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
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
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return null;
  }
}

Future<List<PaymentPlan>> getPaymentPlansServer() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/app/plans',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return [];
    log('getPaymentPlansServer: ${response.body}');
    return PaymentPlan.fromJsonList(jsonDecode(response.body));
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return [];
  }
}

Future<String> getGenratedDescription(String name, String description) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/app/generate-description',
    headers: {},
    body: jsonEncode({'name': name, 'description': description}),
    method: 'POST',
  );
  try {
    if (response == null || response.statusCode != 200) return '';
    log('getGenratedDescription: ${response.body}');
    return jsonDecode(response.body)['description'];
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return '';
  }
}

// API Keys
Future<List<AppApiKey>> listApiKeysServer(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/$appId/keys',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return [];
    log('listApiKeysServer: ${response.body}');
    return AppApiKey.fromJsonList(jsonDecode(response.body));
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return [];
  }
}

Future<Map<String, dynamic>> createApiKeyServer(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/$appId/keys',
    headers: {},
    body: '',
    method: 'POST',
  );
  try {
    if (response == null || response.statusCode != 200) {
      throw Exception('Failed to create apps API key');
    }
    log('createApiKeyServer: ${response.body}');
    return jsonDecode(response.body);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    throw Exception('Failed to create API key: ${e.toString()}');
  }
}

Future<bool> deleteApiKeyServer(String appId, String keyId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/$appId/keys/$keyId',
    headers: {},
    body: '',
    method: 'DELETE',
  );
  try {
    if (response == null || response.statusCode != 200) {
      throw Exception('Failed to delete API key');
    }
    log('deleteApiKeyServer: ${response.body}');
    return true;
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    throw Exception('Failed to delete API key: ${e.toString()}');
  }
}

Future<Map> createPersonaApp(File file, Map<String, dynamic> personaData) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}v1/personas'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));
  request.headers.addAll({'Authorization': await getAuthHeader()});
  request.fields.addAll({'persona_data': jsonEncode(personaData)});
  print(jsonEncode(personaData));
  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      debugPrint('createPersonaApp Response body: ${jsonDecode(response.body)}');
      return jsonDecode(response.body);
    } else {
      debugPrint('Failed to submit app. Status code: ${response.statusCode}');
      return {};
    }
  } catch (e) {
    debugPrint('An error occurred createPersonaApp: $e');
    return {};
  }
}

Future<bool> updatePersonaApp(File? file, Map<String, dynamic> personaData) async {
  var request = http.MultipartRequest(
    'PATCH',
    Uri.parse('${Env.apiBaseUrl}v1/personas/${personaData['id']}'),
  );
  if (file != null) {
    request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));
  }
  request.headers.addAll({'Authorization': await getAuthHeader()});
  request.fields.addAll({'persona_data': jsonEncode(personaData)});
  debugPrint(jsonEncode(personaData));
  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      debugPrint('updatePersonaApp Response body: ${jsonDecode(response.body)}');
      return true;
    } else {
      debugPrint('Failed to update app. Status code: ${response.statusCode}');
      return false;
    }
  } catch (e) {
    debugPrint('An error occurred updatePersonaApp: $e');
    return false;
  }
}

Future<bool> checkPersonaUsername(String username) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/check-username?username=$username',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return false;
    log('checkPersonaUsernames: ${response.body}');
    return jsonDecode(response.body)['is_taken'];
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return true;
  }
}

Future<Map?> getTwitterProfileData(String handle) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/personas/twitter/profile?handle=$handle',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return null;
    log('getTwitterProfileData: ${response.body}');
    return jsonDecode(response.body);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return null;
  }
}

Future<(bool, String?)> verifyTwitterOwnership(String username, String handle, String? personaId) async {
  var url = '${Env.apiBaseUrl}v1/personas/twitter/verify-ownership?username=$username&handle=$handle';
  if (personaId != null) {
    url += '&persona_id=$personaId';
  }
  var response = await makeApiCall(
    url: url,
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return (false, null);
    log('verifyTwitterOwnership: ${response.body}');
    var data = jsonDecode(response.body);
    return (
      (data['verified'] ?? false) as bool,
      data['persona_id'] as String?,
    );
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return (false, null);
  }
}

Future<String> getPersonaInitialMessage(String username) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/personas/twitter/initial-message?username=$username',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return '';
    log('getPersonaInitialMessage: ${response.body}');
    return jsonDecode(response.body)['message'];
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return '';
  }
}

Future<App?> getUserPersonaServer() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/personas',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return null;
    log('getPersonaProfile: ${response.body}');
    var res = jsonDecode(response.body);
    return App.fromJson(res);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return null;
  }
}

Future<String?> generateUsername(String handle) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/personas/generate-username?handle=$handle',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) return null;
    log('generateUsername: ${response.body}');
    var res = jsonDecode(response.body);
    return res['username'];
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return null;
  }
}

Future<bool> migrateAppOwnerId(String oldId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/migrate-owner?old_id=$oldId',
    headers: {},
    body: '',
    method: 'POST',
  );
  try {
    if (response == null || response.statusCode != 200) return false;
    log('migrateAppOwnerId: ${response.body}');
    return true;
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return false;
  }
}

Future<Map<String, dynamic>?> getUpsertUserPersonaServer() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/user/persona',
    headers: {},
    body: '',
    method: 'POST',
  );
  try {
    if (response == null || response.statusCode != 200) return null;
    log('getUpsertUserPersonaServer: ${response.body}');
    return jsonDecode(response.body);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return null;
  }
}
