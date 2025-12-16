import 'dart:convert';
import 'dart:developer';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

Future<List<Map<String, dynamic>>> retrieveAppsGrouped({
  int offset = 0,
  int limit = 10,
  bool includeReviews = false,
}) async {
  final url = '${Env.apiBaseUrl}v2/apps?offset=$offset&limit=$limit&include_reviews=$includeReviews';
  final response = await makeApiCall(
    url: url,
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200 || response.body.isEmpty) return [];
    final data = jsonDecode(response.body) as Map<String, dynamic>;

    // Parse grouped response from backend
    final groups = (data['groups'] as List?) ?? [];
    final List<Map<String, dynamic>> parsed = [];
    for (final g in groups) {
      final capability = g['capability'] as Map<String, dynamic>?;
      final category = g['category'] as Map<String, dynamic>?;
      final pagination = g['pagination'] as Map<String, dynamic>? ?? {};
      final items = (g['data'] as List?) ?? [];
      final apps = App.fromJsonList(items).where((p) => !p.deleted).toList();
      parsed.add({
        'capability': capability,
        'category': category,
        'data': apps,
        'pagination': pagination,
      });
    }
    return parsed;
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return [];
  }
}

Future<({List<App> apps, Map<String, dynamic> pagination, Map<String, dynamic>? category})> retrieveAppsByCategory({
  required String category,
  int offset = 0,
  int limit = 20,
  bool includeReviews = false,
}) async {
  final url = '${Env.apiBaseUrl}v2/apps?category=$category&offset=$offset&limit=$limit&include_reviews=$includeReviews';
  final response = await makeApiCall(
    url: url,
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200 || response.body.isEmpty) {
      return (apps: <App>[], pagination: {'total': 0, 'count': 0, 'offset': offset, 'limit': limit}, category: null);
    }
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final items = (data['data'] as List?) ?? [];
    final apps = App.fromJsonList(items).where((p) => !p.deleted).toList();
    final pagination = (data['pagination'] as Map<String, dynamic>? ?? {});
    final cat = (data['category'] as Map<String, dynamic>?);
    return (apps: apps, pagination: pagination, category: cat);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return (apps: <App>[], pagination: {'total': 0, 'count': 0, 'offset': offset, 'limit': limit}, category: null);
  }
}

Future<({List<App> apps, Map<String, dynamic> pagination, Map<String, dynamic>? capability})> retrieveAppsByCapability({
  required String capability,
  int offset = 0,
  int limit = 20,
  bool includeReviews = false,
}) async {
  final url =
      '${Env.apiBaseUrl}v2/apps?capability=$capability&offset=$offset&limit=$limit&include_reviews=$includeReviews';
  final response = await makeApiCall(
    url: url,
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200 || response.body.isEmpty) {
      return (apps: <App>[], pagination: {'total': 0, 'count': 0, 'offset': offset, 'limit': limit}, capability: null);
    }
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final items = (data['data'] as List?) ?? [];
    final apps = App.fromJsonList(items).where((p) => !p.deleted).toList();
    final pagination = (data['pagination'] as Map<String, dynamic>? ?? {});
    final cap = (data['capability'] as Map<String, dynamic>?);
    return (apps: apps, pagination: pagination, capability: cap);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return (apps: <App>[], pagination: {'total': 0, 'count': 0, 'offset': offset, 'limit': limit}, capability: null);
  }
}

Future<({List<Map<String, dynamic>> groups, Map<String, dynamic>? capability, int totalApps})>
    retrieveCapabilityAppsGroupedByCategory({
  required String capability,
  bool includeReviews = true,
}) async {
  final url = '${Env.apiBaseUrl}v2/apps/capability/$capability/grouped?include_reviews=$includeReviews';
  final response = await makeApiCall(
    url: url,
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200 || response.body.isEmpty) {
      return (groups: <Map<String, dynamic>>[], capability: null, totalApps: 0);
    }
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final groups = (data['groups'] as List?) ?? [];
    final List<Map<String, dynamic>> parsed = [];
    for (final g in groups) {
      final category = g['category'] as Map<String, dynamic>?;
      final items = (g['data'] as List?) ?? [];
      final apps = App.fromJsonList(items).where((p) => !p.deleted).toList();
      final count = g['count'] as int? ?? apps.length;
      parsed.add({
        'category': category,
        'data': apps,
        'count': count,
      });
    }
    final cap = (data['capability'] as Map<String, dynamic>?);
    final meta = (data['meta'] as Map<String, dynamic>?) ?? {};
    final totalApps = meta['totalApps'] as int? ?? 0;
    return (groups: parsed, capability: cap, totalApps: totalApps);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return (groups: <Map<String, dynamic>>[], capability: null, totalApps: 0);
  }
}

Future<({List<App> apps, Map<String, dynamic> pagination, Map<String, dynamic>? filters})> retrieveAppsSearch({
  String? query,
  String? category,
  double? minRating,
  String? capability,
  String? sort,
  bool? myApps,
  bool? installedApps,
  int offset = 0,
  int limit = 50,
}) async {
  // Build URL with query parameters
  final params = <String>[];
  if (query != null && query.isNotEmpty) params.add('q=${Uri.encodeComponent(query)}');
  if (category != null && category.isNotEmpty) params.add('category=${Uri.encodeComponent(category)}');
  if (minRating != null) params.add('rating=$minRating');
  if (capability != null && capability.isNotEmpty) params.add('capability=${Uri.encodeComponent(capability)}');
  if (sort != null && sort.isNotEmpty) params.add('sort=${Uri.encodeComponent(sort)}');
  if (myApps != null) params.add('my_apps=$myApps');
  if (installedApps != null) params.add('installed_apps=$installedApps');
  params.add('offset=$offset');
  params.add('limit=$limit');

  final url = '${Env.apiBaseUrl}v2/apps/search?${params.join('&')}';
  final response = await makeApiCall(
    url: url,
    headers: {},
    body: '',
    method: 'GET',
  );

  try {
    if (response == null || response.statusCode != 200 || response.body.isEmpty) {
      return (
        apps: <App>[],
        pagination: {'total': 0, 'count': 0, 'offset': offset, 'limit': limit},
        filters: null,
      );
    }
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final items = (data['data'] as List?) ?? [];
    final apps = App.fromJsonList(items).where((p) => !p.deleted).toList();
    final pagination = (data['pagination'] as Map<String, dynamic>? ?? {});
    final filters = (data['filters'] as Map<String, dynamic>?);
    return (apps: apps, pagination: pagination, filters: filters);
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return (
      apps: <App>[],
      pagination: {'total': 0, 'count': 0, 'offset': offset, 'limit': limit},
      filters: null,
    );
  }
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
  try {
    var response = await makeMultipartApiCall(
      url: '${Env.apiBaseUrl}v1/app/thumbnails',
      files: [file],
      fileFieldName: 'file',
    );

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
  debugPrint(jsonEncode(appData));
  try {
    var response = await makeMultipartApiCall(
      url: '${Env.apiBaseUrl}v1/apps',
      files: [file],
      fileFieldName: 'file',
      fields: {'app_data': jsonEncode(appData)},
    );

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
  debugPrint(jsonEncode(appData));
  try {
    List<File> files = file != null ? [file] : [];
    var response = await makeMultipartApiCall(
      url: '${Env.apiBaseUrl}v1/apps/${appData['id']}',
      files: files,
      fileFieldName: 'file',
      fields: {'app_data': jsonEncode(appData)},
      method: 'PATCH',
    );

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

/// Generates an app description and a representative emoji.
/// Used by the quick template creator feature.
Future<({String description, String emoji})> getGeneratedDescriptionAndEmoji(String name, String prompt) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/app/generate-description-emoji',
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'name': name, 'prompt': prompt}),
    method: 'POST',
  );
  try {
    if (response == null || response.statusCode != 200) {
      return (description: 'A custom app that $prompt', emoji: '✨');
    }
    log('getGeneratedDescriptionAndEmoji: ${response.body}');
    var data = jsonDecode(response.body);
    return (
      description: (data['description'] as String?) ?? 'A custom app that $prompt',
      emoji: (data['emoji'] as String?) ?? '✨',
    );
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return (description: 'A custom app that $prompt', emoji: '✨');
  }
}

// AI App Generator APIs

/// Fetches AI-generated sample prompts for the app generator
Future<List<String>> getGeneratedAppPrompts() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/app/generate-prompts',
    headers: {},
    body: '',
    method: 'GET',
  );
  try {
    if (response == null || response.statusCode != 200) {
      return [];
    }
    log('getGeneratedAppPrompts: ${response.body}');
    var data = jsonDecode(response.body);
    return (data['prompts'] as List<dynamic>).cast<String>();
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return [];
  }
}

/// Generates app configuration from a natural language prompt using AI
Future<Map<String, dynamic>?> generateAppFromPrompt(String prompt) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/app/generate',
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'prompt': prompt}),
    method: 'POST',
  );
  try {
    if (response == null || response.statusCode != 200) {
      debugPrint('generateAppFromPrompt failed: ${response?.body}');
      return null;
    }
    log('generateAppFromPrompt: ${response.body}');
    var data = jsonDecode(response.body);
    return data['app'] as Map<String, dynamic>;
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return null;
  }
}

/// Generates an app icon using AI (DALL-E)
/// Returns base64 encoded PNG image string
Future<String?> generateAppIcon(String name, String description, String category) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/app/generate-icon',
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      'name': name,
      'description': description,
      'category': category,
    }),
    method: 'POST',
  );
  try {
    if (response == null || response.statusCode != 200) {
      debugPrint('generateAppIcon failed: ${response?.body}');
      return null;
    }
    log('generateAppIcon: success');
    var data = jsonDecode(response.body);
    return data['icon_base64'] as String;
  } catch (e, stackTrace) {
    debugPrint(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return null;
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
  print(jsonEncode(personaData));
  try {
    var response = await makeMultipartApiCall(
      url: '${Env.apiBaseUrl}v1/personas',
      files: [file],
      fileFieldName: 'file',
      fields: {'persona_data': jsonEncode(personaData)},
    );

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
  debugPrint(jsonEncode(personaData));
  try {
    List<File> files = file != null ? [file] : [];
    var response = await makeMultipartApiCall(
      url: '${Env.apiBaseUrl}v1/personas/${personaData['id']}',
      files: files,
      fileFieldName: 'file',
      fields: {'persona_data': jsonEncode(personaData)},
      method: 'PATCH',
    );

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
