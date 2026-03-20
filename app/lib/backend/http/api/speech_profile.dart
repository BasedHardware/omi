import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

class SharedProfile {
  final String sharerUid;
  final String displayName;
  final DateTime createdAt;

  const SharedProfile({
    required this.sharerUid,
    required this.displayName,
    required this.createdAt,
  });

  factory SharedProfile.fromJson(Map<String, dynamic> json) => SharedProfile(
        sharerUid: json['sharer_uid'] as String,
        displayName: json['display_name'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
      );
}

Future<bool> userHasSpeakerProfile() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/speech-profile',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return true;
  Logger.debug('userHasSpeakerProfile: ${response.body}');
  if (response.statusCode == 200) {
    return jsonDecode(response.body)['has_profile'] ?? false;
  }
  return true; // to avoid showing the banner if the request fails or there's no internet.
}

Future<String?> getUserSpeechProfile() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v4/speech-profile',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  Logger.debug('userHasSpeakerProfile: ${response.body}');
  if (response.statusCode == 200) return jsonDecode(response.body)['url'];
  return null;
}

Future<bool> uploadProfile(File file) async {
  try {
    var response = await makeMultipartApiCall(
      url: '${Env.apiBaseUrl}v3/upload-audio',
      files: [file],
      fileFieldName: 'file',
    );

    if (response.statusCode == 200) {
      Logger.debug('uploadProfile Response body: ${jsonDecode(response.body)}');
      return true;
    } else {
      Logger.debug('Failed to upload sample. Status code: ${response.statusCode} body: ${response.body}');
      throw Exception('Failed to upload sample (${response.statusCode}): ${response.body}');
    }
  } catch (e) {
    Logger.debug('An error occurred uploadSample: $e');
    throw Exception('An error occurred uploadSample: $e');
  }
}

Future<List<String>> getExpandedProfileSamples() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/speech-profile/expand',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  Logger.debug('getExpandedProfileSamples: ${response.body}');
  if (response.statusCode == 200) {
    var data = jsonDecode(response.body);
    if (data != null) {
      return List<String>.from(data);
    }
  }
  return [];
}

Future<bool> deleteProfileSample(
  String conversationId,
  int segmentIdx, {
  String? personId,
}) async {
  var response = await makeApiCall(
    url:
        '${Env.apiBaseUrl}v3/speech-profile/expand?memory_id=$conversationId&segment_idx=$segmentIdx&person_id=$personId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('deleteProfileSample: ${response.body}');
  if (response.statusCode == 200) return true;
  return false;
}

// Speech Profile Sharing Functions

Future<void> shareSpeechProfile({
  required String recipientEmail,
  required String displayName,
}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/speech-profile/share',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({
      'recipient_email': recipientEmail,
      'display_name': displayName,
    }),
  );
  
  if (response == null) {
    throw Exception('Failed to share speech profile: No response');
  }
  
  Logger.debug('shareSpeechProfile: ${response.body}');
  if (response.statusCode != 200) {
    final detail = _parseDetail(response.body);
    throw Exception(detail);
  }
}

Future<void> revokeSpeechProfile({required String recipientUserId}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/speech-profile/revoke',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'recipient_user_id': recipientUserId}),
  );
  
  if (response == null) {
    throw Exception('Failed to revoke speech profile: No response');
  }
  
  Logger.debug('revokeSpeechProfile: ${response.body}');
  if (response.statusCode != 200) {
    throw Exception(_parseDetail(response.body));
  }
}

Future<List<SharedProfile>> getSharedProfiles() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/speech-profile/shared',
    headers: {},
    method: 'GET',
    body: '',
  );
  
  if (response == null) return [];
  Logger.debug('getSharedProfiles: ${response.body}');
  
  if (response.statusCode == 200) {
    final List<dynamic> data = jsonDecode(response.body) as List<dynamic>;
    return data
        .map((e) => SharedProfile.fromJson(e as Map<String, dynamic>))
        .toList();
  }
  
  return [];
}

String _parseDetail(String body) {
  try {
    return (jsonDecode(body) as Map<String, dynamic>)['detail'] as String;
  } catch (_) {
    return body;
  }
}
