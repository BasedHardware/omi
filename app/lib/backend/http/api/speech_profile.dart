import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

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
      Logger.debug('Failed to upload sample. Status code: ${response.statusCode}');
      throw Exception('Failed to upload sample. Status code: ${response.statusCode}');
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

/// Returns {'status': 'ok'} on success, or {'error': 'detail message'} on failure.
Future<Map<String, String>> shareSpeechProfile(String targetUid) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile/share',
    headers: {},
    method: 'POST',
    body: jsonEncode({'target_uid': targetUid}),
  );
  Logger.debug('shareSpeechProfile: ${response?.body}');
  if (response != null && response.statusCode == 200) {
    return {'status': 'ok'};
  }
  if (response != null) {
    try {
      final data = jsonDecode(response.body);
      return {'error': data['detail'] ?? 'Unknown error'};
    } catch (_) {}
  }
  return {'error': 'Failed to share speech profile'};
}

Future<bool> revokeSpeechProfile(String targetUid) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile/revoke',
    headers: {},
    method: 'POST',
    body: jsonEncode({'target_uid': targetUid}),
  );
  Logger.debug('revokeSpeechProfile: ${response?.body}');
  return response != null && response.statusCode == 200;
}

Future<bool> removeSharedProfile(String ownerUid) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile/remove-shared',
    headers: {},
    method: 'POST',
    body: jsonEncode({'target_uid': ownerUid}),
  );
  Logger.debug('removeSharedProfile: ${response?.body}');
  return response != null && response.statusCode == 200;
}

class SharedProfileInfo {
  final String uid;
  final String name;

  SharedProfileInfo({required this.uid, required this.name});

  factory SharedProfileInfo.fromJson(Map<String, dynamic> json) {
    return SharedProfileInfo(
      uid: json['uid'] ?? '',
      name: json['name'] ?? '',
    );
  }

  String get displayName => name.isNotEmpty ? name : uid;
}

Future<List<SharedProfileInfo>> getProfilesSharedWithMe() async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile/shared-with-me',
    headers: {},
    method: 'GET',
    body: '',
  );
  Logger.debug('getProfilesSharedWithMe: ${response?.body}');
  if (response != null && response.statusCode == 200) {
    final data = jsonDecode(response.body);
    final list = data['shared_with_me'] as List? ?? [];
    return list.map((item) {
      if (item is Map<String, dynamic>) {
        return SharedProfileInfo.fromJson(item);
      }
      return SharedProfileInfo(uid: item.toString(), name: '');
    }).toList();
  }
  return [];
}

Future<List<SharedProfileInfo>> getUsersIHaveSharedWith() async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile/i-have-shared',
    headers: {},
    method: 'GET',
    body: '',
  );
  Logger.debug('getUsersIHaveSharedWith: ${response?.body}');
  if (response != null && response.statusCode == 200) {
    final data = jsonDecode(response.body);
    final list = data['i_have_shared_with'] as List? ?? [];
    return list.map((item) {
      if (item is Map<String, dynamic>) {
        return SharedProfileInfo.fromJson(item);
      }
      return SharedProfileInfo(uid: item.toString(), name: '');
    }).toList();
  }
  return [];
}
