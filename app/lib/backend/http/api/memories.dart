import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:path/path.dart';

Future<CreateMemoryResponse?> processInProgressMemory() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/memories',
    headers: {},
    method: 'POST',
    body: jsonEncode({}),
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
      },
    );
  }
  return null;
}

Future<List<ServerMemory>> getMemories({int limit = 50, int offset = 0, List<MemoryStatus> statuses = const []}) async {
  var response = await makeApiCall(
      url:
          '${Env.apiBaseUrl}v1/memories?limit=$limit&offset=$offset&statuses=${statuses.map((val) => val.toString().split(".").last).join(",")}',
      headers: {},
      method: 'GET',
      body: '');
  if (response == null) return [];
  if (response.statusCode == 200) {
    // decode body bytes to utf8 string and then parse json so as to avoid utf8 char issues
    var body = utf8.decode(response.bodyBytes);
    var memories = (jsonDecode(body) as List<dynamic>).map((memory) => ServerMemory.fromJson(memory)).toList();
    debugPrint('getMemories length: ${memories.length}');
    return memories;
  } else {
    debugPrint('getMemories error ${response.statusCode}');
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

Future<bool> updateMemoryTitle(String memoryId, String title) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/title?title=$title',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  debugPrint('updateMemoryTitle: ${response.body}');
  return response.statusCode == 200;
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

class TranscriptsResponse {
  List<TranscriptSegment> deepgram;
  List<TranscriptSegment> soniox;
  List<TranscriptSegment> whisperx;
  List<TranscriptSegment> speechmatics;

  TranscriptsResponse({
    this.deepgram = const [],
    this.soniox = const [],
    this.whisperx = const [],
    this.speechmatics = const [],
  });

  factory TranscriptsResponse.fromJson(Map<String, dynamic> json) {
    return TranscriptsResponse(
      deepgram: (json['deepgram'] as List<dynamic>).map((segment) => TranscriptSegment.fromJson(segment)).toList(),
      soniox: (json['soniox'] as List<dynamic>).map((segment) => TranscriptSegment.fromJson(segment)).toList(),
      whisperx: (json['whisperx'] as List<dynamic>).map((segment) => TranscriptSegment.fromJson(segment)).toList(),
      speechmatics:
          (json['speechmatics'] as List<dynamic>).map((segment) => TranscriptSegment.fromJson(segment)).toList(),
    );
  }
}

Future<TranscriptsResponse> getMemoryTranscripts(String memoryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/transcripts',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return TranscriptsResponse();
  debugPrint('getMemoryTranscripts: ${response.body}');
  if (response.statusCode == 200) {
    var transcripts = (jsonDecode(response.body) as Map<String, dynamic>);
    return TranscriptsResponse.fromJson(transcripts);
  }
  return TranscriptsResponse();
}

Future<bool> hasMemoryRecording(String memoryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/recording',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return false;
  debugPrint('getMemoryPhotos: ${response.body}');
  if (response.statusCode == 200) {
    return jsonDecode(response.body)['has_recording'] ?? false;
  }
  return false;
}

Future<bool> assignMemoryTranscriptSegment(
  String memoryId,
  int segmentIdx, {
  bool? isUser,
  String? personId,
  bool useForSpeechTraining = true,
}) async {
  String assignType = isUser != null ? 'is_user' : 'person_id';
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/segments/$segmentIdx/assign?value=${isUser ?? personId}'
        '&assign_type=$assignType&use_for_speech_training=$useForSpeechTraining',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  debugPrint('assignMemoryTranscriptSegment: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setMemoryVisibility(String memoryId, {String visibility = 'shared'}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/visibility?value=$visibility&visibility=$visibility',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  debugPrint('setMemoryVisibility: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setMemoryEventsState(
  String memoryId,
  List<int> eventsIdx,
  List<bool> values,
) async {
  print(jsonEncode({
    'events_idx': eventsIdx,
    'values': values,
  }));
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/events',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({
      'events_idx': eventsIdx,
      'values': values,
    }),
  );
  if (response == null) return false;
  debugPrint('setMemoryEventsState: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setMemoryActionItemState(
  String memoryId,
  List<int> actionItemsIdx,
  List<bool> values,
) async {
  print(jsonEncode({
    'items_idx': actionItemsIdx,
    'values': values,
  }));
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/action-items',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({
      'items_idx': actionItemsIdx,
      'values': values,
    }),
  );
  if (response == null) return false;
  debugPrint('setMemoryActionItemState: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> deleteMemoryActionItem(String memoryId, ActionItem item) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/action-items',
    headers: {},
    method: 'DELETE',
    body: jsonEncode({
      'completed': item.completed,
      'description': item.description,
    }),
  );
  if (response == null) return false;
  debugPrint('deleteMemoryActionItem: ${response.body}');
  return response.statusCode == 204;
}

//this is expected to return complete memories
Future<List<ServerMemory>> sendStorageToBackend(File file, String sdCardDateTimeString) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}sdcard_memory?date_time=$sdCardDateTimeString'),
  );
  request.headers.addAll({'Authorization': await getAuthHeader()});
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));
  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      debugPrint('storageSend Response body: ${jsonDecode(response.body)}');
    } else {
      debugPrint('Failed to storageSend. Status code: ${response.statusCode}');
      return [];
    }

    var memories = (jsonDecode(response.body) as List<dynamic>).map((memory) => ServerMemory.fromJson(memory)).toList();
    debugPrint('getMemories length: ${memories.length}');

    return memories;
  } catch (e) {
    debugPrint('An error occurred storageSend: $e');
    return [];
  }
}

Future<SyncLocalFilesResponse> syncLocalFiles(List<File> files) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}v1/sync-local-files'),
  );
  for (var file in files) {
    request.files.add(await http.MultipartFile.fromPath('files', file.path, filename: basename(file.path)));
  }
  request.headers.addAll({'Authorization': await getAuthHeader()});

  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      debugPrint('syncLocalFile Response body: ${jsonDecode(response.body)}');
      return SyncLocalFilesResponse.fromJson(jsonDecode(response.body));
    } else {
      debugPrint('Failed to upload sample. Status code: ${response.statusCode}');
      throw Exception('Failed to upload sample. Status code: ${response.statusCode}');
    }
  } catch (e) {
    debugPrint('An error occurred uploadSample: $e');
    throw Exception('An error occurred uploadSample: $e');
  }
}
