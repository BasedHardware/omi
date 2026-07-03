import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/device_speech_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

Future<bool> userHasSpeakerProfile() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v3/speech-profile', headers: {}, method: 'GET', body: '');
  if (response == null) return true;
  Logger.debug('userHasSpeakerProfile: ${response.body}');
  if (response.statusCode == 200) {
    return wire.GeneratedHasSpeechProfileResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).hasProfile;
  }
  return true; // to avoid showing the banner if the request fails or there's no internet.
}

Future<String?> getUserSpeechProfile() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v4/speech-profile', headers: {}, method: 'GET', body: '');
  if (response == null) return null;
  Logger.debug('userHasSpeakerProfile: ${response.body}');
  if (response.statusCode == 200) {
    return wire.GeneratedSpeechProfileResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>).url;
  }
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
      final data = wire.GeneratedSpeechProfileUploadResponse.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
      Logger.debug('uploadProfile Response url: ${data.url}');
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
    return wire.GeneratedExpandedSpeechProfileSamplesResponse.fromJsonList(
      jsonDecode(response.body) as List<dynamic>,
    ).items;
  }
  return [];
}

Future<bool> deleteProfileSample(String conversationId, int segmentIdx, {String? personId}) async {
  var response = await makeApiCall(
    url:
        '${Env.apiBaseUrl}v3/speech-profile/expand?memory_id=$conversationId&segment_idx=$segmentIdx&person_id=$personId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('deleteProfileSample: ${response.body}');
  if (response.statusCode == 200) {
    final data = wire.GeneratedSpeechProfileMutationResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    return data.status == 'ok';
  }
  return false;
}
