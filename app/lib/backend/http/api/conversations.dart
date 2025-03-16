import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:path/path.dart';

Future<CreateConversationResponse?> processInProgressConversation() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/memories',
    headers: {},
    method: 'POST',
    body: jsonEncode({}),
  );
  if (response == null) return null;
  debugPrint('createConversationServer: ${response.body}');
  if (response.statusCode == 200) {
    return CreateConversationResponse.fromJson(jsonDecode(response.body));
  } else {
    // TODO: Server returns 304 doesn't recover
    CrashReporting.reportHandledCrash(
      Exception('Failed to create conversation'),
      StackTrace.current,
      level: NonFatalExceptionLevel.info,
      userAttributes: {
        'response': response.body,
      },
    );
  }
  return null;
}

Future<List<ServerConversation>> getConversations(
    {int limit = 50,
    int offset = 0,
    List<ConversationStatus> statuses = const [],
    bool includeDiscarded = true}) async {
  var response = await makeApiCall(
      url:
          '${Env.apiBaseUrl}v1/memories?include_discarded=$includeDiscarded&limit=$limit&offset=$offset&statuses=${statuses.map((val) => val.toString().split(".").last).join(",")}',
      headers: {},
      method: 'GET',
      body: '');
  if (response == null) return [];
  if (response.statusCode == 200) {
    // decode body bytes to utf8 string and then parse json so as to avoid utf8 char issues
    var body = utf8.decode(response.bodyBytes);
    var memories =
        (jsonDecode(body) as List<dynamic>).map((conversation) => ServerConversation.fromJson(conversation)).toList();
    debugPrint('getMemories length: ${memories.length}');
    return memories;
  } else {
    debugPrint('getMemories error ${response.statusCode}');
  }
  return [];
}

Future<ServerConversation?> reProcessConversationServer(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId/reprocess',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return null;
  debugPrint('reProcessConversationServer: ${response.body}');
  if (response.statusCode == 200) {
    return ServerConversation.fromJson(jsonDecode(response.body));
  }
  return null;
}

Future<bool> deleteConversationServer(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  debugPrint('deleteConversation: ${response.statusCode}');
  return response.statusCode == 204;
}

Future<ServerConversation?> getConversationById(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getConversationById: ${response.body}');
  if (response.statusCode == 200) {
    return ServerConversation.fromJson(jsonDecode(response.body));
  }
  return null;
}

Future<bool> updateConversationTitle(String conversationId, String title) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId/title?title=$title',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  debugPrint('updateConversationTitle: ${response.body}');
  return response.statusCode == 200;
}

Future<List<ConversationPhoto>> getConversationPhotos(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId/photos',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  debugPrint('getConversationPhotos: ${response.body}');
  if (response.statusCode == 200) {
    return (jsonDecode(response.body) as List<dynamic>).map((photo) => ConversationPhoto.fromJson(photo)).toList();
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

Future<TranscriptsResponse> getConversationTranscripts(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId/transcripts',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return TranscriptsResponse();
  debugPrint('getConversationTranscripts: ${response.body}');
  if (response.statusCode == 200) {
    var transcripts = (jsonDecode(response.body) as Map<String, dynamic>);
    return TranscriptsResponse.fromJson(transcripts);
  }
  return TranscriptsResponse();
}

Future<bool> hasConversationRecording(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId/recording',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return false;
  debugPrint('hasConversationRecording: ${response.body}');
  if (response.statusCode == 200) {
    return jsonDecode(response.body)['has_recording'] ?? false;
  }
  return false;
}

Future<bool> assignConversationTranscriptSegment(
  String conversationId,
  int segmentIdx, {
  bool? isUser,
  String? personId,
  bool useForSpeechTraining = true,
}) async {
  String assignType = isUser != null ? 'is_user' : 'person_id';
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId/segments/$segmentIdx/assign?value=${isUser ?? personId}'
        '&assign_type=$assignType&use_for_speech_training=$useForSpeechTraining',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  debugPrint('assignConversationTranscriptSegment: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> assignConversationSpeaker(
  String conversationId,
  int speakerId,
  bool isUser, {
  String? personId,
  bool useForSpeechTraining = true,
}) async {
  String assignType = isUser ? 'is_user' : 'person_id';
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId/assign-speaker/$speakerId?value=${isUser ? 'true' : personId}'
        '&assign_type=$assignType&use_for_speech_training=$useForSpeechTraining',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  debugPrint('assignConversationSpeaker: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setConversationVisibility(String conversationId, {String visibility = 'shared'}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId/visibility?value=$visibility&visibility=$visibility',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  debugPrint('setConversationVisibility: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setConversationEventsState(
  String conversationId,
  List<int> eventsIdx,
  List<bool> values,
) async {
  print(jsonEncode({
    'events_idx': eventsIdx,
    'values': values,
  }));
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId/events',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({
      'events_idx': eventsIdx,
      'values': values,
    }),
  );
  if (response == null) return false;
  debugPrint('setConversationEventsState: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setConversationActionItemState(
  String conversationId,
  List<int> actionItemsIdx,
  List<bool> values,
) async {
  print(jsonEncode({
    'items_idx': actionItemsIdx,
    'values': values,
  }));
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId/action-items',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({
      'items_idx': actionItemsIdx,
      'values': values,
    }),
  );
  if (response == null) return false;
  debugPrint('setConversationActionItemState: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> deleteConversationActionItem(String conversationId, ActionItem item) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$conversationId/action-items',
    headers: {},
    method: 'DELETE',
    body: jsonEncode({
      'completed': item.completed,
      'description': item.description,
    }),
  );
  if (response == null) return false;
  debugPrint('deleteConversationActionItem: ${response.body}');
  return response.statusCode == 204;
}

//this is expected to return complete memories
Future<List<ServerConversation>> sendStorageToBackend(File file, String sdCardDateTimeString) async {
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

    var memories = (jsonDecode(response.body) as List<dynamic>)
        .map((conversation) => ServerConversation.fromJson(conversation))
        .toList();
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

Future<(List<ServerConversation>, int, int)> searchConversationsServer(
  String query, {
  int? page,
  int? limit,
  bool includeDiscarded = true,
}) async {
  debugPrint(Env.apiBaseUrl);
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/search',
    headers: {},
    method: 'POST',
    body:
        jsonEncode({'query': query, 'page': page ?? 1, 'per_page': limit ?? 10, 'include_discarded': includeDiscarded}),
  );
  if (response == null) return (<ServerConversation>[], 0, 0);
  if (response.statusCode == 200) {
    List<dynamic> items = (jsonDecode(response.body))['items'];
    int currentPage = (jsonDecode(response.body))['current_page'];
    int totalPages = (jsonDecode(response.body))['total_pages'];
    var convos = items.map<ServerConversation>((item) => ServerConversation.fromJson(item)).toList();
    return (convos, currentPage, totalPages);
  }
  return (<ServerConversation>[], 0, 0);
}
