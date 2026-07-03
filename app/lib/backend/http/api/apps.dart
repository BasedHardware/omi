import 'dart:convert';
import 'dart:developer';
import 'dart:io';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/gen/apps_wire.g.dart' as wire;
import 'package:omi/backend/schema/gen/misc_wire.g.dart' as misc_wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

Category _categoryFromWire(wire.GeneratedAppSelectOption option) {
  return Category(title: option.title, id: option.id);
}

PaymentPlan _paymentPlanFromWire(wire.GeneratedAppSelectOption option) {
  return PaymentPlan(title: option.title, id: option.id);
}

AppCapability _appCapabilityFromWire(wire.GeneratedAppCapabilityResponse capability) {
  final triggers = capability.triggers ?? const <wire.GeneratedAppSelectOption>[];
  final scopes = capability.scopes ?? const <wire.GeneratedAppSelectOption>[];
  final actions = capability.actions ?? const <wire.GeneratedAppCapabilityAction>[];
  return AppCapability(
    title: capability.title,
    id: capability.id,
    triggerEvents: triggers.map((event) => TriggerEvent(title: event.title, id: event.id)).toList(),
    notificationScopes: scopes.map((scope) => NotificationScope(title: scope.title, id: scope.id)).toList(),
    actions: actions
        .map(
          (action) => CapacityAction(
            title: action.title,
            id: action.id,
            docUrl: action.docUrl,
            description: action.description,
          ),
        )
        .toList(),
  );
}

Map<String, dynamic> _paginationToJson(wire.GeneratedAppPagination? pagination, int offset, int limit) {
  return pagination?.toJson() ?? {'total': 0, 'count': 0, 'offset': offset, 'limit': limit};
}

Future<List<Map<String, dynamic>>> retrieveAppsGrouped({
  int offset = 0,
  int limit = 10,
  bool includeReviews = false,
}) async {
  final url = '${Env.apiBaseUrl}v2/apps?offset=$offset&limit=$limit&include_reviews=$includeReviews';
  final response = await makeApiCall(url: url, headers: {}, body: '', method: 'GET');
  try {
    if (response == null || response.statusCode != 200 || response.body.isEmpty) return [];
    final data = wire.GeneratedAppCatalogResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);

    final List<Map<String, dynamic>> parsed = [];
    for (final group in data.groups ?? const <wire.GeneratedAppCatalogGroup>[]) {
      final apps = (group.data ?? const <wire.GeneratedAppBaseModel>[])
          .map(App.fromGenerated)
          .where((app) => !app.deleted)
          .toList();
      parsed.add({
        'capability': group.capability?.toJson(),
        'category': group.category?.toJson(),
        'data': apps,
        'pagination': _paginationToJson(group.pagination, offset, limit),
      });
    }
    return parsed;
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
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
  final response = await makeApiCall(url: url, headers: {}, body: '', method: 'GET');
  try {
    if (response == null || response.statusCode != 200 || response.body.isEmpty) {
      return (apps: <App>[], pagination: {'total': 0, 'count': 0, 'offset': offset, 'limit': limit}, category: null);
    }
    final data = wire.GeneratedAppCatalogResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    final apps = (data.data ?? const <wire.GeneratedAppBaseModel>[])
        .map(App.fromGenerated)
        .where((p) => !p.deleted)
        .toList();
    final pagination = _paginationToJson(data.pagination, offset, limit);
    final cat = data.category?.toJson();
    return (apps: apps, pagination: pagination, category: cat);
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return (apps: <App>[], pagination: {'total': 0, 'count': 0, 'offset': offset, 'limit': limit}, category: null);
  }
}

Future<({List<Map<String, dynamic>> groups, Map<String, dynamic>? capability, int totalApps})>
retrieveCapabilityAppsGroupedByCategory({required String capability, bool includeReviews = true}) async {
  final url = '${Env.apiBaseUrl}v2/apps/capability/$capability/grouped?include_reviews=$includeReviews';
  final response = await makeApiCall(url: url, headers: {}, body: '', method: 'GET');
  try {
    if (response == null || response.statusCode != 200 || response.body.isEmpty) {
      return (groups: <Map<String, dynamic>>[], capability: null, totalApps: 0);
    }
    final data = wire.GeneratedAppCatalogResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    final List<Map<String, dynamic>> parsed = [];
    for (final group in data.groups ?? const <wire.GeneratedAppCatalogGroup>[]) {
      final apps = (group.data ?? const <wire.GeneratedAppBaseModel>[])
          .map(App.fromGenerated)
          .where((app) => !app.deleted)
          .toList();
      final count = group.count ?? apps.length;
      parsed.add({'category': group.category?.toJson(), 'data': apps, 'count': count});
    }
    final cap = data.capability?.toJson();
    final totalApps = data.meta?.totalApps ?? 0;
    return (groups: parsed, capability: cap, totalApps: totalApps);
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
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
  final response = await makeApiCall(url: url, headers: {}, body: '', method: 'GET');

  try {
    if (response == null || response.statusCode != 200 || response.body.isEmpty) {
      return (apps: <App>[], pagination: {'total': 0, 'count': 0, 'offset': offset, 'limit': limit}, filters: null);
    }
    final data = wire.GeneratedAppSearchResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    final apps = (data.data ?? const <wire.GeneratedAppBaseModel>[])
        .map(App.fromGenerated)
        .where((p) => !p.deleted)
        .toList();
    final pagination = data.pagination.toJson();
    final filters = data.filters.toJson();
    return (apps: apps, pagination: pagination, filters: filters);
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return (apps: <App>[], pagination: {'total': 0, 'count': 0, 'offset': offset, 'limit': limit}, filters: null);
  }
}

Future<List<App>> retrievePopularApps() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/apps/popular', headers: {}, body: '', method: 'GET');
  if (response != null && response.statusCode == 200 && response.body.isNotEmpty) {
    try {
      log('apps: ${response.body}');
      var apps = (jsonDecode(response.body) as List<dynamic>)
          .map((item) => App.fromGenerated(wire.GeneratedAppBaseModel.fromJson(item as Map<String, dynamic>)))
          .toList();
      apps = apps.where((p) => !p.deleted).toList();
      SharedPreferencesUtil().appsList = apps;
      return apps;
    } catch (e, stackTrace) {
      Logger.debug(e.toString());
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
      return SharedPreferencesUtil().appsList;
    }
  }
  return SharedPreferencesUtil().appsList;
}

Future<List<String>> getEnabledAppsServer() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/apps/enabled', headers: {}, body: '', method: 'GET');
  try {
    if (response == null || response.statusCode != 200) return [];
    return wire.GeneratedEnabledAppsResponse.fromJsonList(jsonDecode(response.body) as List<dynamic>).items;
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return [];
  }
}

Future<bool> enableAppServer(String appId) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/apps/enable?app_id=$appId',
      headers: {},
      method: 'POST',
      body: '',
    );
    if (response == null || response.statusCode != 200) return false;
    Logger.debug('enableAppServer: $appId ${response.body}');
    final data = wire.GeneratedAppMutationResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return data.status == 'ok';
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return false;
  }
}

Future<bool> disableAppServer(String appId) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/apps/disable?app_id=$appId',
      headers: {},
      method: 'POST',
      body: '',
    );
    if (response == null || response.statusCode != 200) return false;
    Logger.debug('disableAppServer: ${response.body}');
    final data = wire.GeneratedAppMutationResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return data.status == 'ok';
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return false;
  }
}

Future<bool> reviewApp(String appId, AppReview review) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/apps/review?app_id=$appId',
      headers: {'Content-Type': 'application/json'},
      method: 'POST',
      body: jsonEncode(review.toJson()),
    );
    Logger.debug('reviewApp: ${response?.body}');
    if (response == null || response.statusCode != 200) return false;
    final data = wire.GeneratedAppMutationResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return data.status == 'ok';
  } catch (e) {
    Logger.debug('Error reviewing app: $e');
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
      final data = wire.GeneratedAppThumbnailUploadResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      return {'thumbnail_url': data.thumbnailUrl, 'thumbnail_id': data.thumbnailId};
    } else {
      Logger.debug('Failed to upload thumbnail. Status code: ${response.statusCode}');
      return {};
    }
  } catch (e) {
    Logger.debug('An error occurred uploading thumbnail: $e');
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
    Logger.debug('updateAppReview: ${response?.body}');
    return response?.statusCode == 200;
  } catch (e) {
    Logger.debug('Error updating app review: $e');
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
    Logger.debug('replyToAppReview: ${response?.body}');
    return response?.statusCode == 200;
  } catch (e) {
    Logger.debug('Error replying to app review: $e');
    return false;
  }
}

Future<String> getAppMarkdown(String appMarkdownPath) async {
  var response = await makeApiCall(url: appMarkdownPath, method: 'GET', headers: {}, body: '');
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
  try {
    final data = jsonDecode(response?.body ?? '{}') as Map<String, dynamic>;
    Logger.debug(data);
    return data['is_setup_completed'] ?? false;
  } on FormatException catch (e) {
    Logger.debug('Response not a valid json: $e');
    return false;
  } catch (e) {
    Logger.debug('Error triggering request at endpoint: $e');
    return false;
  }
}

Future<(bool, String, String?)> submitAppServer(File file, Map<String, dynamic> appData) async {
  Logger.debug(jsonEncode(appData));
  try {
    var response = await makeMultipartApiCall(
      url: '${Env.apiBaseUrl}v1/apps',
      files: [file],
      fileFieldName: 'file',
      fields: {'app_data': jsonEncode(appData)},
    );

    if (response.statusCode == 200) {
      final respData = wire.GeneratedAppCreateResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      String appId = respData.appId;
      Logger.debug('submitAppServer Response body: $respData');
      return (true, '', appId);
    } else {
      Logger.debug('Failed to submit app. Status code: ${response.statusCode}');
      if (response.body.isNotEmpty) {
        final error = misc_wire.GeneratedErrorResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
        return (false, error.detail is String ? error.detail as String : 'Failed to submit app', null);
      } else {
        return (false, 'Failed to submit app. Please try again later', '');
      }
    }
  } catch (e) {
    Logger.debug('An error occurred submitAppServer: $e');
    return (false, 'Failed to submit app. Please try again later', null);
  }
}

Future<bool> updateAppServer(File? file, Map<String, dynamic> appData) async {
  Logger.debug(jsonEncode(appData));
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
      final data = wire.GeneratedAppMutationResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      Logger.debug('updateAppServer status: ${data.status}');
      return data.status == 'ok';
    } else {
      Logger.debug('Failed to update app. Status code: ${response.statusCode}');
      return false;
    }
  } catch (e) {
    Logger.debug('An error occurred updateAppServer: $e');
    return false;
  }
}

Future<List<Category>> getAppCategories() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/app-categories', headers: {}, body: '', method: 'GET');
  try {
    if (response == null || response.statusCode != 200) return [];
    log('getAppCategories: ${response.body}');
    final res = jsonDecode(response.body) as List;
    return res
        .map((item) => wire.GeneratedAppSelectOption.fromJson(item as Map<String, dynamic>))
        .map(_categoryFromWire)
        .toList();
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return [];
  }
}

Future<List<AppCapability>> getAppCapabilitiesServer() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/app-capabilities', headers: {}, body: '', method: 'GET');
  try {
    if (response == null || response.statusCode != 200) return [];
    log('getAppCapabilities: ${response.body}');
    final res = jsonDecode(response.body) as List;
    return res
        .map((item) => wire.GeneratedAppCapabilityResponse.fromJson(item as Map<String, dynamic>))
        .map(_appCapabilityFromWire)
        .toList();
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
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
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return false;
  }
}

Future<bool> refreshAppManifestServer(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/$appId/refresh-manifest',
    headers: {},
    body: '',
    method: 'POST',
  );
  try {
    if (response == null || response.statusCode != 200) return false;
    log('refreshAppManifestServer: ${response.body}');
    return true;
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return false;
  }
}

Future deleteAppServer(String appId) async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/apps/$appId', headers: {}, body: '', method: 'DELETE');
  try {
    if (response == null || response.statusCode != 200) return false;
    log('deleteAppServer: ${response.body}');
    return true;
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return false;
  }
}

Future<Map<String, dynamic>?> getAppDetailsServer(String appId) async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/apps/$appId', headers: {}, body: '', method: 'GET');
  try {
    if (response == null || response.statusCode != 200) return null;
    log('getAppDetailsServer: ${response.body}');
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    wire.GeneratedApp.fromJson(data);
    return data;
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return null;
  }
}

Future<List<PaymentPlan>> getPaymentPlansServer() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/app/plans', headers: {}, body: '', method: 'GET');
  try {
    if (response == null || response.statusCode != 200) return [];
    log('getPaymentPlansServer: ${response.body}');
    final res = jsonDecode(response.body) as List;
    return res
        .map((item) => wire.GeneratedAppSelectOption.fromJson(item as Map<String, dynamic>))
        .map(_paymentPlanFromWire)
        .toList();
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
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
    return wire.GeneratedAppDescriptionGenerationResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).description;
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
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
    final data = wire.GeneratedAppDescriptionEmojiGenerationResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    return (description: data.description, emoji: data.emoji);
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
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
    return wire.GeneratedAppPromptsGenerationResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).prompts;
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
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
      Logger.debug('generateAppFromPrompt failed: ${response?.body}');
      return null;
    }
    log('generateAppFromPrompt: ${response.body}');
    final data = wire.GeneratedAppGenerationResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return data.app.toJson();
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
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
    body: jsonEncode({'name': name, 'description': description, 'category': category}),
    method: 'POST',
  );
  try {
    if (response == null || response.statusCode != 200) {
      Logger.debug('generateAppIcon failed: ${response?.body}');
      return null;
    }
    log('generateAppIcon: success');
    return wire.GeneratedAppIconGenerationResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).iconBase64;
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return null;
  }
}

// API Keys
Future<List<AppApiKey>> listApiKeysServer(String appId) async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/apps/$appId/keys', headers: {}, body: '', method: 'GET');
  try {
    if (response == null || response.statusCode != 200) return [];
    log('listApiKeysServer: ${response.body}');
    return (jsonDecode(response.body) as List)
        .map((item) => wire.GeneratedAppApiKeyResponse.fromJson(item as Map<String, dynamic>))
        .map(AppApiKey.fromGenerated)
        .toList();
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return [];
  }
}

Future<Map<String, dynamic>> createApiKeyServer(String appId) async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/apps/$appId/keys', headers: {}, body: '', method: 'POST');
  try {
    if (response == null || response.statusCode != 200) {
      throw Exception('Failed to create apps API key');
    }
    log('createApiKeyServer: ${response.body}');
    return wire.GeneratedAppApiKeyResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>).toJson();
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
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
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    throw Exception('Failed to delete API key: ${e.toString()}');
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
    final data = wire.GeneratedAppMigrationResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return data.status == 'ok';
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return false;
  }
}

/// Add an MCP server as a private app with chat tools.
/// Returns {app_id, requires_oauth, auth_url?, tools_count?, tool_names?}
Future<Map<String, dynamic>?> addMcpServer(String name, String serverUrl, {String? description}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/mcp',
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      'name': name,
      'mcp_server_url': serverUrl,
      if (description != null && description.isNotEmpty) 'description': description,
    }),
    method: 'POST',
  );
  try {
    if (response == null) return null;
    Logger.debug('addMcpServer: ${response.statusCode} ${response.body}');
    if (response.statusCode == 200) {
      return wire.GeneratedMcpAddServerResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>).toJson();
    }
    // Return error detail
    try {
      final error = misc_wire.GeneratedErrorResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      return {'error': error.detail is String ? error.detail : 'Failed to add MCP server'};
    } catch (_) {
      return {'error': 'Failed to add MCP server (${response.statusCode})'};
    }
  } catch (e, stackTrace) {
    Logger.debug(e.toString());
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
    return null;
  }
}
