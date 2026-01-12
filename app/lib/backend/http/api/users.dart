import 'dart:convert';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';

Future<bool> updateUserGeolocation({required Geolocation geolocation}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/geolocation',
    headers: {},
    method: 'PATCH',
    body: jsonEncode(geolocation.toJson()),
  );
  if (response == null) return false;
  if (response.statusCode == 200) return true;
  return false;
}

Future<bool> setUserWebhookUrl({required String type, required String url}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/developer/webhook/$type',
    headers: {},
    method: 'POST',
    body: jsonEncode({'url': url}),
  );
  if (response == null) return false;
  if (response.statusCode == 200) return true;
  return false;
}

Future<String> getUserWebhookUrl({required String type}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/developer/webhook/$type',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return '';
  if (response.statusCode == 200) {
    var jsonResponse = jsonDecode(response.body);
    return (jsonResponse['url'] as String?) ?? '';
  }
  return '';
}

Future disableWebhook({required String type}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/developer/webhook/$type/disable',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  if (response.statusCode == 204) return true;
  return false;
}

Future enableWebhook({required String type}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/developer/webhook/$type/enable',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  if (response.statusCode == 204) return true;
  return false;
}

Future webhooksStatus() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/developer/webhooks/status',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  }
  return null;
}

Future<bool> deleteAccount() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/delete-account',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  debugPrint('deleteAccount response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setRecordingPermission(bool value) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/store-recording-permission?value=$value',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  debugPrint('storeRecordingPermission response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool?> getStoreRecordingPermission() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/store-recording-permission',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getStoreRecordingPermission response: ${response.body}');
  if (response.statusCode == 200) {
    var jsonResponse = jsonDecode(response.body);
    return jsonResponse['store_recording_permission'] as bool?;
  }
  return null;
}

Future<bool> deletePermissionAndRecordings() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/store-recording-permission',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  debugPrint('deletePermissionAndRecordings response: ${response.body}');
  return response.statusCode == 200;
}

/**/

Future<bool> setPrivateCloudSyncEnabled(bool value) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/private-cloud-sync?value=$value',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  debugPrint('setPrivateCloudSyncEnabled response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> getPrivateCloudSyncEnabled() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/private-cloud-sync',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return false;
  debugPrint('getPrivateCloudSyncEnabled response: ${response.body}');
  if (response.statusCode == 200) {
    var jsonResponse = jsonDecode(response.body);
    return jsonResponse['private_cloud_sync_enabled'] as bool? ?? false;
  }
  return false;
}

Future<Person?> createPerson(String name) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/people',
    headers: {},
    method: 'POST',
    body: jsonEncode({'name': name}),
  );
  if (response == null) return null;
  debugPrint('createPerson response: ${response.body}');
  if (response.statusCode == 200) {
    return Person.fromJson(jsonDecode(response.body));
  }
  return null;
}

Future<Person?> getSinglePerson(String personId, {bool includeSpeechSamples = false}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/people/$personId?include_speech_samples=$includeSpeechSamples',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getSinglePerson response: ${response.body}');
  if (response.statusCode == 200) {
    return Person.fromJson(jsonDecode(response.body));
  }
  return null;
}

Future<List<Person>> getAllPeople({bool includeSpeechSamples = true}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/people?include_speech_samples=$includeSpeechSamples',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  if (response.statusCode == 200) {
    List<dynamic> peopleJson = jsonDecode(response.body);
    List<Person> people = peopleJson.mapIndexed((idx, json) {
      json['color_idx'] = idx % speakerColors.length;
      return Person.fromJson(json);
    }).toList();
    // sort by name
    people.sort((a, b) => a.name.compareTo(b.name));
    return people;
  }
  return [];
}

Future<bool> updatePersonName(String personId, String newName) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/people/$personId/name?value=$newName',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  debugPrint('updatePersonName response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> deletePerson(String personId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/people/$personId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  debugPrint('deletePerson response: ${response.body}');
  return response.statusCode == 204;
}

Future<bool> deletePersonSpeechSample(String personId, int sampleIndex) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/people/$personId/speech-samples/$sampleIndex',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  debugPrint('deletePersonSpeechSample response: ${response.body}');
  return response.statusCode == 200;
}

Future<String> getFollowUpQuestion({String conversationId = '0'}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/joan/$conversationId/followup-question',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return '';
  debugPrint('getFollowUpQuestion response: ${response.body}');
  if (response.statusCode == 200) {
    var jsonResponse = jsonDecode(response.body);
    return jsonResponse['result'] as String? ?? '';
  }
  return '';
}

/*Analytics*/

Future<bool> setConversationSummaryRating(String conversationId, int value, {String? reason}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/analytics/memory_summary?memory_id=$conversationId&value=$value&reason=$reason',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  debugPrint('setConversationSummaryRating response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setMessageResponseRating(String messageId, int value, {String? reason}) async {
  // Build URL with required params
  String url = '${Env.apiBaseUrl}v1/users/analytics/chat_message?message_id=$messageId&value=$value';
  
  // Add reason param if provided (for thumbs down feedback)
  if (reason != null && reason.isNotEmpty) {
    url += '&reason=$reason';
  }
  
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  debugPrint('setMessageResponseRating response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> getHasConversationSummaryRating(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/analytics/memory_summary?memory_id=$conversationId',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return false;
  debugPrint('getHasConversationSummaryRating response: ${response.body}');

  try {
    var jsonResponse = jsonDecode(response.body);
    return jsonResponse['has_rating'] as bool? ?? false;
  } catch (e) {
    return false;
  }
}

// User language preference API calls
Future<String?> getUserPrimaryLanguage() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/language',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getUserPrimaryLanguage response: ${response.body}');

  try {
    var jsonResponse = jsonDecode(response.body);
    // Return null if language is null or empty
    if (jsonResponse['language'] == null || jsonResponse['language'] == '') {
      return null;
    }
    return jsonResponse['language'] as String?;
  } catch (e) {
    debugPrint('Error parsing getUserPrimaryLanguage response: $e');
    return null;
  }
}

Future<bool> setUserPrimaryLanguage(String languageCode) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/language',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({'language': languageCode}),
  );
  if (response == null) return false;
  debugPrint('setUserPrimaryLanguage response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setPreferredSummarizationAppServer(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/preferences/app?app_id=$appId',
    headers: {},
    method: 'PUT',
    body: '',
  );
  if (response == null) return false;
  debugPrint('setPreferredSummarizationAppServer response: ${response.body}');
  return response.statusCode == 200;
}

Future<UserUsageResponse?> getUserUsage({required String period}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/me/usage?period=$period',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getUserUsage response: ${response.body}');
  if (response.statusCode == 200) {
    return UserUsageResponse.fromJson(jsonDecode(response.body));
  }
  return null;
}

Future<Map<String, dynamic>> getTrainingDataOptIn() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/training-data-opt-in',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return {'opted_in': false, 'status': null};
  debugPrint('getTrainingDataOptIn response: ${response.body}');
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  }
  return {'opted_in': false, 'status': null};
}

Future<bool> setTrainingDataOptIn() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/training-data-opt-in',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  debugPrint('setTrainingDataOptIn response: ${response.body}');
  return response.statusCode == 200;
}

// Transcription Preferences

Future<Map<String, dynamic>?> getTranscriptionPreferences() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/transcription-preferences',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getTranscriptionPreferences response: ${response.body}');
  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  }
  return null;
}

Future<bool> setTranscriptionPreferences({
  bool? singleLanguageMode,
  List<String>? vocabulary,
}) async {
  Map<String, dynamic> body = {};
  if (singleLanguageMode != null) {
    body['single_language_mode'] = singleLanguageMode;
  }
  if (vocabulary != null) {
    body['vocabulary'] = vocabulary;
  }

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/transcription-preferences',
    headers: {},
    method: 'PATCH',
    body: jsonEncode(body),
  );
  if (response == null) return false;
  debugPrint('setTranscriptionPreferences response: ${response.body}');
  return response.statusCode == 200;
}

Future<UserSubscriptionResponse?> getUserSubscription() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/me/subscription',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getUserSubscription response: ${response.body}');
  if (response.statusCode == 200) {
    return UserSubscriptionResponse.fromJson(jsonDecode(response.body));
  }
  return null;
}

// Daily Summary Settings

class DailySummarySettings {
  final bool enabled;
  final int hour; // Local hour (0-23)

  DailySummarySettings({required this.enabled, required this.hour});

  factory DailySummarySettings.fromJson(Map<String, dynamic> json) {
    return DailySummarySettings(
      enabled: json['enabled'] ?? true,
      hour: json['hour'] ?? 22, // Default to 10 PM
    );
  }
}

Future<DailySummarySettings?> getDailySummarySettings() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/daily-summary-settings',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getDailySummarySettings response: ${response.body}');
  if (response.statusCode == 200) {
    return DailySummarySettings.fromJson(jsonDecode(response.body));
  }
  return null;
}

Future<bool> setDailySummarySettings({bool? enabled, int? hour}) async {
  Map<String, dynamic> body = {};
  if (enabled != null) {
    body['enabled'] = enabled;
  }
  if (hour != null) {
    body['hour'] = hour;
  }

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/daily-summary-settings',
    headers: {},
    method: 'PATCH',
    body: jsonEncode(body),
  );
  if (response == null) return false;
  debugPrint('setDailySummarySettings response: ${response.body}');
  return response.statusCode == 200;
}

// Daily Summaries API

Future<List<DailySummary>> getDailySummaries({int limit = 30, int offset = 0}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/daily-summaries?limit=$limit&offset=$offset',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200) return [];

  try {
    final data = jsonDecode(response.body);
    final summaries = (data['summaries'] as List<dynamic>?)?.map((e) => DailySummary.fromJson(e)).toList() ?? [];
    return summaries;
  } catch (e) {
    debugPrint('Error parsing daily summaries: $e');
    return [];
  }
}

Future<DailySummary?> getDailySummary(String summaryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/daily-summaries/$summaryId',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200) return null;

  try {
    final data = jsonDecode(response.body);
    return DailySummary.fromJson(data);
  } catch (e) {
    debugPrint('Error parsing daily summary: $e');
    return null;
  }
}

Future<bool> deleteDailySummary(String summaryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/daily-summaries/$summaryId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  return response?.statusCode == 200;
}

/// Generate a daily summary for a specific date (or today if not specified)
/// Returns the summary_id on success, null on failure
Future<String?> generateDailySummary({String? date}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/daily-summary-settings/test',
    headers: {},
    method: 'POST',
    body: date != null ? jsonEncode({'date': date}) : '',
  );
  if (response == null || response.statusCode != 200) return null;

  try {
    final data = jsonDecode(response.body);
    return data['summary_id'] as String?;
  } catch (e) {
    debugPrint('Error parsing generate summary response: $e');
    return null;
  }
}
