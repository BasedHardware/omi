import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart';

Future<bool> userHasSpeakerProfile() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/speech-profile',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return true;
  debugPrint('userHasSpeakerProfile: ${response.body}');
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
  debugPrint('userHasSpeakerProfile: ${response.body}');
  if (response.statusCode == 200) return jsonDecode(response.body)['url'];
  return null;
}

Future<bool> uploadProfile(File file) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}v3/upload-audio'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));
  request.headers.addAll({'Authorization': await getAuthHeader()});

  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      debugPrint('uploadProfile Response body: ${jsonDecode(response.body)}');
      return true;
    } else {
      debugPrint('Failed to upload sample. Status code: ${response.statusCode}');
      throw Exception('Failed to upload sample. Status code: ${response.statusCode}');
    }
  } catch (e) {
    debugPrint('An error occurred uploadSample: $e');
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
  debugPrint('getExpandedProfileSamples: ${response.body}');
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
  debugPrint('deleteProfileSample: ${response.body}');
  if (response.statusCode == 200) return true;
  return false;
}
