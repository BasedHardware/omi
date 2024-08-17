import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart';

Future<bool> userHasSpeakerProfile() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/speech-profile',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return false;
  debugPrint('userHasSpeakerProfile: ${response.body}');
  if (response.statusCode == 200) {
    return jsonDecode(response.body)['has_profile'] ?? false;
  }
  return true; // to avoid showing the banner if the request fails or there's no internet.
}

// Future<List<SpeakerIdSample>> getUserSamplesState() async {
//   debugPrint('getUserSamplesState for uid: ${SharedPreferencesUtil().uid}');
//   var response = await makeApiCall(
//     url: '${Env.apiBaseUrl}v1/speech-profile/samples',
//     headers: {},
//     method: 'GET',
//     body: '',
//   );
//   if (response == null) return [];
//   debugPrint('getUserSamplesState: ${response.body}');
//   return SpeakerIdSample.fromJsonList(jsonDecode(response.body));
// }

Future<bool> uploadProfileBytes(List<List<int>> bytes, int duration) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/upload-bytes',
    headers: {},
    body: jsonEncode({'bytes': bytes, 'duration': duration}),
    method: 'POST',
  );
  debugPrint('uploadProfileBytes: ${response?.body}');
  if (response == null) return false;
  if (response.statusCode != 200) return false;
  return true;
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
