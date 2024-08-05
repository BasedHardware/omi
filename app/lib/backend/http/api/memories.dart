import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:tuple/tuple.dart';

Future<void> migrateMemoriesToBackend(List<dynamic> memories) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/migration/memories',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode(memories),
  );
  debugPrint('migrateMemoriesToBackend: ${response?.body}');
}

Future<CreateMemoryResponse?> createMemoryServer({
  required DateTime startedAt,
  required DateTime finishedAt,
  required List<TranscriptSegment> transcriptSegments,
  Geolocation? geolocation,
  List<Tuple2<String, String>> photos = const [],
  bool triggerIntegrations = true,
}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories?language_code=${SharedPreferencesUtil().recordingsLanguage}&trigger_integrations=$triggerIntegrations',
    headers: {},
    method: 'POST',
    body: jsonEncode({
      'started_at': startedAt.toIso8601String(),
      'finished_at': finishedAt.toIso8601String(),
      'transcript_segments': transcriptSegments.map((segment) => segment.toJson()).toList(),
      'geolocation': geolocation?.toJson(),
      'photos': photos.map((photo) => {'base63': photo.item1, 'description': photo.item2}).toList(),
    }),
  );
  if (response == null) return null; // TODO: if fails should tell, do something
  debugPrint('createMemoryServer: ${response.body}');
  if (response.statusCode == 200) {
    return CreateMemoryResponse.fromJson(jsonDecode(response.body));
  } else {
    CrashReporting.reportHandledCrash(
      Exception('Failed to create memory'),
      StackTrace.current,
      level: NonFatalExceptionLevel.info,
      userAttributes: {
        'response': response.body,
        'transcriptSegments': TranscriptSegment.segmentsAsString(transcriptSegments),
      },
    );
  }
  return null;
}

Future<List<ServerMemory>> getMemories({int limit = 50, int offset = 0}) async {
  var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/memories?limit=$limit&offset=$offset', headers: {}, method: 'GET', body: '');
  if (response == null) return [];
  if (response.statusCode == 200) {
    var memories = (jsonDecode(response.body) as List<dynamic>).map((memory) => ServerMemory.fromJson(memory)).toList();
    debugPrint('getMemories length: ${memories.length}');
    return memories;
  }
  return [];
}

Future<ServerMemory?> reProcessMemoryServer(String memoryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/reprocess?language_code=${SharedPreferencesUtil().recordingsLanguage}',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return null;
  debugPrint('reProcessMemoryServer: ${response.body}');
  if (response.statusCode == 200) {
    return ServerMemory.fromJson(jsonDecode(response.body));
  }
  return null;
}

Future<bool> deleteMemoryServer(String memoryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  debugPrint('deleteMemory: ${response.statusCode}');
  return response.statusCode == 204;
}

Future<ServerMemory?> getMemoryById(String memoryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getMemoryById: ${response.body}');
  if (response.statusCode == 200) {
    return ServerMemory.fromJson(jsonDecode(response.body));
  }
  return null;
}
