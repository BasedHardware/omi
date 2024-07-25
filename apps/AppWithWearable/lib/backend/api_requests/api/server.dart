import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/shared.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/backend/schema/sample.dart';
import 'package:friend_private/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:instabug_http_client/instabug_http_client.dart';
import 'package:path/path.dart';

Future<List<TranscriptSegment>> transcribe(File file) async {
  final client = InstabugHttpClient();
  var request = http.MultipartRequest(
    'POST',
    Uri.parse(
        '${Env.apiBaseUrl}v1/transcribe?language=${SharedPreferencesUtil().recordingsLanguage}&uid=${SharedPreferencesUtil().uid}'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));
  request.headers.addAll({
    'Authorization': await getAuthHeader(),
  });

  try {
    var startTime = DateTime.now();
    var streamedResponse = await client.send(request);
    var response = await http.Response.fromStream(streamedResponse);
    debugPrint('Transcript server took: ${DateTime.now().difference(startTime).inSeconds} seconds');
    if (response.statusCode == 200) {
      var data = jsonDecode(response.body);
      debugPrint('Response body: ${response.body}');
      return TranscriptSegment.fromJsonList(data);
    } else {
      throw Exception('Failed to upload file. Status code: ${response.statusCode} Body: ${response.body}');
    }
  } catch (e) {
    rethrow;
  }
}

Future<bool> userHasSpeakerProfile(String uid) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile?uid=$uid',
    // url: 'https://5818-107-3-134-29.ngrok-free.app/v1/speech-profile',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return false;
  debugPrint('userHasSpeakerProfile: ${response.body}');
  return jsonDecode(response.body)['has_profile'] ?? false;
}

Future<List<SpeakerIdSample>> getUserSamplesState(String uid) async {
  debugPrint('getUserSamplesState for uid: $uid');
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
  debugPrint('uploadSample ${file.path} for uid: $uid');
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
    url: '${Env.apiBaseUrl}v1/backups?uid=${SharedPreferencesUtil().uid}',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'data': backup}),
  );
  debugPrint('uploadBackup: ${response?.body}');
}

Future<String> downloadBackupApi(String uid) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/backups?uid=$uid',
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
    url: '${Env.apiBaseUrl}v1/backups?uid=${SharedPreferencesUtil().uid}',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  debugPrint('deleteBackup: ${response.body}');
  return response.statusCode == 200;
}

Future<List<Plugin>> retrievePlugins() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugins?uid=${SharedPreferencesUtil().uid}',
    headers: {},
    body: '',
    method: 'GET',
  );
  if (response?.statusCode == 200) {
    try {
      var plugins = Plugin.fromJsonList(jsonDecode(response!.body));
      SharedPreferencesUtil().pluginsList = plugins;
      return plugins;
    } catch (e, stackTrace) {
      debugPrint(e.toString());
      CrashReporting.reportHandledCrash(e, stackTrace);
      return SharedPreferencesUtil().pluginsList;
    }
  }
  return SharedPreferencesUtil().pluginsList;
}

Future<void> reviewPlugin(String pluginId, double score, {String review = ''}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/plugins/review?plugin_id=$pluginId&uid=${SharedPreferencesUtil().uid}',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'score': score, review: review}),
  );
  debugPrint('reviewPlugin: ${response?.body}');
}

Future<void> migrateUserServer(String prevUid, String newUid) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}migrate-user?prev_uid=$prevUid&new_uid=$newUid',
    headers: {},
    method: 'POST',
    body: '',
  );
  debugPrint('migrateUser: ${response?.body}');
}
