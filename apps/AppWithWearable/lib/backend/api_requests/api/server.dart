import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/shared.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/sample.dart';
import 'package:friend_private/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:instabug_http_client/instabug_http_client.dart';
import 'package:path/path.dart';

Future<List<TranscriptSegment>> transcribeAudioFile(File file, String uid) async {
  final client = InstabugHttpClient();
  var request = http.MultipartRequest(
    'POST',
    Uri.parse(
        '${Env.apiBaseUrl}transcribe?language=${SharedPreferencesUtil().recordingsLanguage}&uid=$uid'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));

  try {
    var startTime = DateTime.now();
    var streamedResponse = await client.send(request);
    var response = await http.Response.fromStream(streamedResponse);
    debugPrint('TranscribeAudioFile took: ${DateTime.now().difference(startTime).inSeconds} seconds');
    if (response.statusCode == 200) {
      var data = jsonDecode(response.body);
      debugPrint('Response body: ${response.body}');
      return TranscriptSegment.fromJsonList(data);
    } else {
      throw Exception('Failed to upload file. Status code: ${response.statusCode} Body: ${response.body}');
    }
  } catch (e, stackTrace) {
    CrashReporting.reportHandledCrash(e, stackTrace);
    throw Exception('An error occurred transcribeAudioFile: $e');
  }
}

Future<bool> userHasSpeakerProfile(String uid) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}profile?uid=$uid',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return false;
  debugPrint('userHasSpeakerProfile: ${response.body}');
  return jsonDecode(response.body)['has_profile'] ?? false;
}

Future<List<SpeakerIdSample>> getUserSamplesState(String uid) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}samples?uid=$uid',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  debugPrint('getUserSamplesState: ${response.body}');
  return SpeakerIdSample.fromJsonList(jsonDecode(response.body));
}

Future<bool> uploadSample(File file, String uid) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}samples/upload?uid=$uid'),
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

Future<void> uploadBackupApi(String backup) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}backup?uid=${SharedPreferencesUtil().uid}',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'data': backup}),
  );
  debugPrint('uploadBackup: ${response?.body}');
}

Future<String> downloadBackupApi(String uid) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}backup?uid=$uid',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return '';
  debugPrint('downloadBackup: ${response.body}');
  return jsonDecode(response.body)['data'] ?? '';
}

Future<bool> deleteBackupApi() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}backup?uid=${SharedPreferencesUtil().uid}',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  debugPrint('deleteBackup: ${response.body}');
  return response.statusCode == 200;
}
