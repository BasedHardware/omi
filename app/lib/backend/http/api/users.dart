import 'dart:convert';
import 'dart:io';

import 'package:collection/collection.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/gen/misc_wire.g.dart' as misc_wire;
import 'package:omi/backend/schema/gen/people_wire.g.dart' as people_wire;
import 'package:omi/backend/schema/gen/subscription_usage_wire.g.dart' as subscription_wire;
import 'package:omi/backend/schema/gen/users_wire.g.dart' as wire;
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/utils/logger.dart';

Future<bool> updateUserGeolocation({required Geolocation geolocation}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/geolocation',
    headers: {},
    method: 'PATCH',
    body: jsonEncode(geolocation.toJson()),
  );
  if (response == null) return false;
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
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
    final data = wire.GeneratedUserWebhookUrlResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return data.url ?? '';
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
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    return wire.GeneratedUserWebhooksStatusResponse.fromJson(decoded).toJson();
  }
  return null;
}

Future<bool> deleteAccount({String? reason, String? reasonDetails}) async {
  final hasFeedback = (reason != null && reason.isNotEmpty) || (reasonDetails != null && reasonDetails.isNotEmpty);
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/delete-account',
    headers: hasFeedback ? {'Content-Type': 'application/json'} : {},
    method: 'DELETE',
    body: hasFeedback ? jsonEncode({'reason': reason, 'reason_details': reasonDetails}) : '',
  );
  if (response == null) return false;
  Logger.debug('deleteAccount response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
}

Future<bool> setRecordingPermission(bool value) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/store-recording-permission?value=$value',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('storeRecordingPermission response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
}

Future<bool?> getStoreRecordingPermission() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/store-recording-permission',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  Logger.debug('getStoreRecordingPermission response: ${response.body}');
  if (response.statusCode == 200) {
    return wire.GeneratedStoreRecordingPermissionResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).storeRecordingPermission;
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
  Logger.debug('deletePermissionAndRecordings response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
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
  Logger.debug('setPrivateCloudSyncEnabled response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
}

/// Returns the server's private-cloud-sync flag, or `null` when the value
/// could not be fetched (no response / non-200). Never coerce a fetch failure
/// into `false` — callers must preserve the last known state instead of
/// silently flipping the toggle off on a transient network error.
Future<bool?> getPrivateCloudSyncEnabled() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/private-cloud-sync',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  Logger.debug('getPrivateCloudSyncEnabled response: ${response.body}');
  if (response.statusCode == 200) {
    return wire.GeneratedPrivateCloudSyncResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).privateCloudSyncEnabled;
  }
  return null;
}

Future<Person?> createPerson(String name) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/people',
    headers: {},
    method: 'POST',
    body: jsonEncode({'name': name}),
  );
  if (response == null) return null;
  Logger.debug('createPerson response: ${response.body}');
  if (response.statusCode == 200) {
    return Person.fromGenerated(
      people_wire.GeneratedPerson.fromJson(jsonDecode(response.body) as Map<String, dynamic>),
    );
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
      return Person.fromGenerated(
        people_wire.GeneratedPerson.fromJson(json as Map<String, dynamic>),
        colorIdx: idx % speakerColors.length,
      );
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
  Logger.debug('updatePersonName response: ${response.body}');
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
  Logger.debug('deletePerson response: ${response.body}');
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
  Logger.debug('deletePersonSpeechSample response: ${response.body}');
  return response.statusCode == 200;
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
  Logger.debug('setConversationSummaryRating response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
}

Future<bool> setMessageResponseRating(String messageId, int value, {String? reason}) async {
  // Build URL with required params
  String url = '${Env.apiBaseUrl}v1/users/analytics/chat_message?message_id=$messageId&value=$value';

  // Add reason param if provided (for thumbs down feedback)
  if (reason != null && reason.isNotEmpty) {
    url += '&reason=$reason';
  }

  var response = await makeApiCall(url: url, headers: {}, method: 'POST', body: '');
  if (response == null) return false;
  Logger.debug('setMessageResponseRating response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
}

Future<bool> getHasConversationSummaryRating(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/analytics/memory_summary?memory_id=$conversationId',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('getHasConversationSummaryRating response: ${response.body}');

  try {
    return wire.GeneratedMemorySummaryRatingResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).hasRating;
  } catch (e) {
    return false;
  }
}

// User language preference API calls
Future<String?> getUserPrimaryLanguage() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/users/language', headers: {}, method: 'GET', body: '');
  if (response == null) return null;
  Logger.debug('getUserPrimaryLanguage response: ${response.body}');

  try {
    final jsonResponse = wire.GeneratedUserLanguageResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    // Return null if language is null or empty
    if (jsonResponse.language == null || jsonResponse.language == '') {
      return null;
    }
    return jsonResponse.language;
  } catch (e) {
    Logger.debug('Error parsing getUserPrimaryLanguage response: $e');
    return null;
  }
}

/// Returns the server-decided `single_language_mode` on success, null on
/// failure. The server derives eligibility from the live STT capability
/// policy (#10022) — clients must not re-decide it locally.
Future<bool?> setUserPrimaryLanguage(String languageCode) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/language',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({'language': languageCode}),
  );
  if (response == null) return null;
  Logger.debug('setUserPrimaryLanguage response: ${response.body}');
  if (response.statusCode != 200) return null;
  final data = wire.GeneratedUserLanguageUpdateResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  if (data.status != 'ok') return null;
  return data.singleLanguageMode;
}

Future<bool> setPreferredSummarizationAppServer(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/preferences/app?app_id=$appId',
    headers: {},
    method: 'PUT',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('setPreferredSummarizationAppServer response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
}

Future<UserUsageResponse?> getUserUsage({required String period}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/me/usage?period=$period',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  Logger.debug('getUserUsage response: ${response.body}');
  if (response.statusCode == 200) {
    return UserUsageResponse.fromGenerated(
      subscription_wire.GeneratedUserUsageResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>),
    );
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
  Logger.debug('getTrainingDataOptIn response: ${response.body}');
  if (response.statusCode == 200) {
    return wire.GeneratedTrainingDataOptInResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>).toJson();
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
  Logger.debug('setTrainingDataOptIn response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
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
  Logger.debug('getTranscriptionPreferences response: ${response.body}');
  if (response.statusCode == 200) {
    return wire.GeneratedTranscriptionPreferencesResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).toJson();
  }
  return null;
}

Future<bool> setTranscriptionPreferences({bool? singleLanguageMode, List<String>? vocabulary}) async {
  final body = wire.GeneratedTranscriptionPreferencesUpdate(
    singleLanguageMode: singleLanguageMode,
    vocabulary: vocabulary,
  );

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/transcription-preferences',
    headers: {},
    method: 'PATCH',
    body: jsonEncode(body.toJson()),
  );
  if (response == null) return false;
  Logger.debug('setTranscriptionPreferences response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
}

Future<UserSubscriptionResponse?> getUserSubscription() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/me/subscription',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  Logger.debug('getUserSubscription response: ${response.body}');
  if (response.statusCode == 200) {
    return UserSubscriptionResponse.fromGenerated(
      subscription_wire.GeneratedUserSubscriptionResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>),
    );
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
  Logger.debug('getDailySummarySettings response: ${response.body}');
  if (response.statusCode == 200) {
    final data = wire.GeneratedDailySummarySettingsResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return DailySummarySettings(enabled: data.enabled, hour: data.hour);
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
  Logger.debug('setDailySummarySettings response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
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
    final data = wire.GeneratedDailySummariesResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return data.summaries?.map(DailySummary.fromGenerated).toList() ?? [];
  } catch (e) {
    Logger.debug('Error parsing daily summaries: $e');
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
    final data = wire.GeneratedDailySummaryResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return DailySummary.fromGenerated(data);
  } catch (e) {
    Logger.debug('Error parsing daily summary: $e');
    return null;
  }
}

Future<bool> setDailySummaryVisibility(String summaryId, {String visibility = 'shared'}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/daily-summaries/$summaryId/visibility?value=$visibility',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null || response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status.toLowerCase() == 'ok';
}

/// Regenerate a daily summary in place. Backend re-runs generation for the
/// summary's date and overwrites the same doc. Returns the refreshed
/// summary on success, null on failure.
/// Backend route: POST /v1/users/daily-summaries/{summary_id}/regenerate.
/// Returns a `RegenerateResult` carrying the new summary or a structured
/// error so the UI can distinguish "no conversations" / cooldown / other.
class RegenerateDailySummaryResult {
  final DailySummary? summary;
  final int? statusCode;
  final String? errorDetail;

  RegenerateDailySummaryResult({this.summary, this.statusCode, this.errorDetail});

  bool get success => summary != null;
}

Future<RegenerateDailySummaryResult> regenerateDailySummary(String summaryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/daily-summaries/$summaryId/regenerate',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) {
    return RegenerateDailySummaryResult(statusCode: null, errorDetail: null);
  }
  if (response.statusCode != 200) {
    String? detail;
    try {
      final body = misc_wire.GeneratedErrorResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      if (body.detail is String) detail = body.detail as String;
    } catch (_) {}
    return RegenerateDailySummaryResult(statusCode: response.statusCode, errorDetail: detail);
  }
  try {
    final data = wire.GeneratedDailySummaryResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return RegenerateDailySummaryResult(summary: DailySummary.fromGenerated(data), statusCode: 200);
  } catch (e) {
    Logger.debug('Error parsing regenerated daily summary: $e');
    return RegenerateDailySummaryResult(statusCode: 200);
  }
}

/// Delete a daily summary by id. Returns true on success.
/// Backend route: DELETE /v1/users/daily-summaries/{summary_id}.
Future<bool> deleteDailySummary(String summaryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/daily-summaries/$summaryId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  // 200 = deleted, 404 = already gone (treat as success — user expectation matches).
  if (response.statusCode == 404) return true;
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
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
    final data = wire.GeneratedDailySummaryTestResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return data.summaryId;
  } catch (e) {
    Logger.debug('Error parsing generate summary response: $e');
    return null;
  }
}

// Onboarding State

Future<Map<String, dynamic>?> getUserOnboardingState() async {
  print('DEBUG getUserOnboardingState: calling ${Env.apiBaseUrl}v1/users/onboarding');
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/users/onboarding', headers: {}, method: 'GET', body: '');
  print('DEBUG getUserOnboardingState: response=${response?.statusCode}, body=${response?.body}');
  if (response == null) return null;
  if (response.statusCode == 200) {
    return wire.GeneratedOnboardingStateResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>).toJson();
  }
  return null;
}

Future<bool> updateUserOnboardingState({
  bool? completed,
  String? acquisitionSource,
  bool? deviceOnboardingCompleted,
}) async {
  Map<String, dynamic> body = {};
  if (completed != null) {
    body['completed'] = completed;
  }
  if (acquisitionSource != null) {
    body['acquisition_source'] = acquisitionSource;
  }
  if (deviceOnboardingCompleted != null) {
    body['device_onboarding_completed'] = deviceOnboardingCompleted;
  }

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/onboarding',
    headers: {},
    method: 'PATCH',
    body: jsonEncode(body),
  );
  if (response == null) return false;
  Logger.debug('updateUserOnboardingState response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
}

// Mentor Notification Settings

class MentorNotificationSettings {
  final int frequency; // 0-5 where 0=disabled, 1=most selective, 5=most proactive

  MentorNotificationSettings({required this.frequency});

  factory MentorNotificationSettings.fromJson(Map<String, dynamic> json) {
    return MentorNotificationSettings(
      frequency: json['frequency'] ?? 0, // Default to 0 (disabled)
    );
  }
}

Future<MentorNotificationSettings?> getMentorNotificationSettings() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/mentor-notification-settings',
    headers: {},
    method: 'GET',
    body: '',
  );

  Logger.debug('getMentorNotificationSettings response: ${response?.body}');
  if (response != null && response.statusCode == 200) {
    final data = wire.GeneratedMentorNotificationSettingsResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    return MentorNotificationSettings(frequency: data.frequency);
  }
  return null;
}

Future<bool> setMentorNotificationSettings(int frequency) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/mentor-notification-settings',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({'frequency': frequency}),
  );
  if (response == null) return false;

  Logger.debug('setMentorNotificationSettings response: ${response.body}');
  if (response.statusCode != 200) return false;
  final data = wire.GeneratedUserStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  return data.status == 'ok';
}

/// Streams the /v1/users/export endpoint directly to a file, avoiding loading
/// the entire JSON into memory. Returns the file path on success, null on failure.
Future<String?> exportUserDataToFile(String filePath) async {
  try {
    final response = await makeRawApiCall(url: '${Env.apiBaseUrl}v1/users/export', method: 'GET');
    if (response.statusCode != 200) {
      Logger.debug('exportUserDataToFile failed: ${response.statusCode}');
      return null;
    }
    final file = File(filePath);
    final sink = file.openWrite();
    await for (final chunk in response.stream) {
      sink.add(chunk);
    }
    await sink.flush();
    await sink.close();
    return filePath;
  } catch (e) {
    Logger.debug('exportUserDataToFile error: $e');
    return null;
  }
}

Future<Map<String, dynamic>?> getFairUseStatus() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/fair-use/status', headers: {}, method: 'GET', body: '');
  if (response == null) return null;
  Logger.debug('getFairUseStatus response: ${response.statusCode}');
  if (response.statusCode == 200) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    return wire.GeneratedFairUseStatusResponse.fromJson(decoded).toJson();
  }
  return null;
}
