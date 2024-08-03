import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/sample.dart';
import 'package:friend_private/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart';

Future<bool> userHasSpeakerProfile() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile?uid=${SharedPreferencesUtil().uid}',
    // url: 'https://5818-107-3-134-29.ngrok-free.app/v1/speech-profile',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return false;
  debugPrint('userHasSpeakerProfile: ${response.body}');
  return jsonDecode(response.body)['has_profile'] ?? false;
}

Future<List<SpeakerIdSample>> getUserSamplesState() async {
  debugPrint('getUserSamplesState for uid: ${SharedPreferencesUtil().uid}');
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}samples?uid=${SharedPreferencesUtil().uid}',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  debugPrint('getUserSamplesState: ${response.body}');
  return SpeakerIdSample.fromJsonList(jsonDecode(response.body));
}

Future<bool> uploadSample(File file) async {
  debugPrint('uploadSample ${file.path} for uid: ${SharedPreferencesUtil().uid}');
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}samples/upload?uid=${SharedPreferencesUtil().uid}'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));

  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      debugPrint('uploadSample Response body: ${jsonDecode(response.body)}');
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
