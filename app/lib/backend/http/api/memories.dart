import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/http/webhooks.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:path/path.dart';
import 'package:tuple/tuple.dart';

Future<bool> migrateMemoriesToBackend(List<dynamic> memories) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/migration/memories',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode(memories),
  );
  debugPrint('migrateMemoriesToBackend: ${response?.body}');
  return response?.statusCode == 200;
}

Future<CreateMemoryResponse?> createMemoryServer({
  required DateTime startedAt,
  required DateTime finishedAt,
  required List<TranscriptSegment> transcriptSegments,
  Geolocation? geolocation,
  List<Tuple2<String, String>> photos = const [],
  bool triggerIntegrations = true,
  String? language,
  File? audioFile,
}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories?trigger_integrations=$triggerIntegrations',
    headers: {},
    method: 'POST',
    body: jsonEncode({
      'started_at': startedAt.toIso8601String(),
      'finished_at': finishedAt.toIso8601String(),
      'transcript_segments': transcriptSegments.map((segment) => segment.toJson()).toList(),
      'geolocation': geolocation?.toJson(),
      'photos': photos.map((photo) => {'base64': photo.item1, 'description': photo.item2}).toList(),
      'source': transcriptSegments.isNotEmpty ? 'friend' : 'openglass',
      'language': language, // maybe determine auto?
      // 'audio_base64_url': audioFile != null ? await wavToBase64Url(audioFile.path) : null,
    }),
  );
  if (response == null) return null;
  debugPrint('createMemoryServer: ${response.body}');
  if (response.statusCode == 200) {
    return CreateMemoryResponse.fromJson(jsonDecode(response.body));
  } else {
    // TODO: Server returns 304 doesn't recover
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

Future<ServerMemory> memoryPostProcessing(File file, String memoryId) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}v1/memories/$memoryId/post-processing'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));
  request.headers.addAll({'Authorization': await getAuthHeader()});

  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      debugPrint('memoryPostProcessing Response body: ${jsonDecode(response.body)}');
      return ServerMemory.fromJson(jsonDecode(response.body));
    } else {
      debugPrint('Failed to memoryPostProcessing. Status code: ${response.statusCode}');
      throw Exception('Failed to memoryPostProcessing. Status code: ${response.statusCode}');
    }
  } catch (e) {
    debugPrint('An error occurred memoryPostProcessing: $e');
    throw Exception('An error occurred memoryPostProcessing: $e');
  }
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
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/reprocess',
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

Future<List<MemoryPhoto>> getMemoryPhotos(String memoryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/photos',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  debugPrint('getMemoryPhotos: ${response.body}');
  if (response.statusCode == 200) {
    return (jsonDecode(response.body) as List<dynamic>).map((photo) => MemoryPhoto.fromJson(photo)).toList();
  }
  return [];
}
