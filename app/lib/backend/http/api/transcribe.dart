import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart';

// DEPRECATED
Future<List<TranscriptSegment>> transcribe(File file) async {
  final client = http.Client();
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
