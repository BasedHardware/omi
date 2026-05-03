import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

Future<CreateConversationResponse?> processInProgressConversation() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations',
    headers: {},
    method: 'POST',
    body: jsonEncode({}),
  );
  if (response == null) return null;
  Logger.debug('createConversationServer: ${response.body}');
  if (response.statusCode == 200) {
    return CreateConversationResponse.fromJson(jsonDecode(response.body));
  } else {
    // TODO: Server returns 304 doesn't recover
    PlatformManager.instance.crashReporter.reportCrash(
      Exception('Failed to create conversation'),
      StackTrace.current,
      userAttributes: {'response': response.body},
    );
  }
  return null;
}

Future<List<ServerConversation>> getConversations({
  int limit = 50,
  int offset = 0,
  List<ConversationStatus> statuses = const [],
  bool includeDiscarded = true,
  DateTime? startDate,
  DateTime? endDate,
  String? folderId,
  bool? starred,
}) async {
  String url =
      '${Env.apiBaseUrl}v1/conversations?include_discarded=$includeDiscarded&limit=$limit&offset=$offset&statuses=${statuses.map((val) => val.toString().split(".").last).join(",")}';

  // Add date filters if provided
  if (startDate != null) {
    url += '&start_date=${startDate.toUtc().toIso8601String()}';
  }
  if (endDate != null) {
    url += '&end_date=${endDate.toUtc().toIso8601String()}';
  }
  if (folderId != null) {
    url += '&folder_id=$folderId';
  }
  if (starred != null) {
    url += '&starred=$starred';
  }

  var response = await makeApiCall(url: url, headers: {}, method: 'GET', body: '');
  if (response == null) return [];
  if (response.statusCode == 200) {
    // decode body bytes to utf8 string and then parse json so as to avoid utf8 char issues
    var body = utf8.decode(response.bodyBytes);
    var memories =
        (jsonDecode(body) as List<dynamic>).map((conversation) => ServerConversation.fromJson(conversation)).toList();
    Logger.debug('getConversations length: ${memories.length}');
    return memories;
  } else {
    Logger.debug('getConversations error ${response.statusCode}');
  }
  return [];
}

Future<ServerConversation?> reProcessConversationServer(String conversationId, {String? appId}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/reprocess${appId != null ? '?app_id=$appId' : ''}',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return null;
  Logger.debug('reProcessConversationServer: ${response.body}');
  if (response.statusCode == 200) {
    return ServerConversation.fromJson(jsonDecode(response.body));
  }
  return null;
}

Future<bool> deleteConversationServer(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId?cascade=true',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('deleteConversation: ${response.statusCode}');
  return response.statusCode == 204;
}

Future<ServerConversation?> getConversationById(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    return ServerConversation.fromJson(jsonDecode(response.body));
  } else if (response.statusCode == 402) {
    Logger.debug('Unlimited Plan Required for conversation: $conversationId');
    return null;
  }
  return null;
}

Future<bool> updateConversationTitle(String conversationId, String title) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/title?title=$title',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('updateConversationTitle: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> updateConversationSegmentText(String conversationId, String segmentId, String text) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/segments/text',
    headers: {'Content-Type': 'application/json'},
    method: 'PATCH',
    body: jsonEncode({'segment_id': segmentId, 'text': text}),
  );
  if (response == null) return false;
  return response.statusCode == 200;
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
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/transcripts',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return TranscriptsResponse();
  Logger.debug('getConversationTranscripts: ${response.body}');
  if (response.statusCode == 200) {
    var transcripts = (jsonDecode(response.body) as Map<String, dynamic>);
    return TranscriptsResponse.fromJson(transcripts);
  }
  return TranscriptsResponse();
}

Future<bool> assignBulkConversationTranscriptSegments(
  String conversationId,
  List<String> segmentIds, {
  bool? isUser,
  String? personId,
}) async {
  String assignType;
  String? value;
  if (isUser == true) {
    assignType = 'is_user';
    value = 'true';
  } else {
    assignType = 'person_id';
    value = personId; // can be null for un-assign
  }

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/segments/assign-bulk',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({'segment_ids': segmentIds, 'assign_type': assignType, 'value': value}),
  );
  if (response == null) return false;
  Logger.debug('assignBulkConversationTranscriptSegments: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setConversationVisibility(String conversationId, {String visibility = 'shared'}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/visibility?value=$visibility',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('setConversationVisibility: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setConversationStarred(String conversationId, bool starred) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/starred?starred=$starred',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('setConversationStarred: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> setConversationActionItemState(String conversationId, List<int> actionItemsIdx, List<bool> values) async {
  print(jsonEncode({'items_idx': actionItemsIdx, 'values': values, 'conversation_id': conversationId}));
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/action-items',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({'items_idx': actionItemsIdx, 'values': values}),
  );
  if (response == null) return false;
  Logger.debug('setConversationActionItemState: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> updateActionItemDescription(
  String conversationId,
  String oldDescription,
  String newDescription,
  int idx,
) async {
  var body = {'old_description': oldDescription, 'description': newDescription};
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/action-items/$idx',
    headers: {},
    method: 'PATCH',
    body: jsonEncode(body),
  );
  if (response == null) return false;
  Logger.debug('updateActionItemDescription: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> deleteConversationActionItem(String conversationId, ActionItem item) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/action-items',
    headers: {},
    method: 'DELETE',
    body: jsonEncode({'completed': item.completed, 'description': item.description}),
  );
  if (response == null) return false;
  Logger.debug('deleteConversationActionItem: ${response.body}');
  return response.statusCode == 204;
}

/// v2 async sync: POST files → 202 with job_id, then poll until terminal.
/// Returns the same SyncLocalFilesResponse as v1 once processing is confirmed complete.
typedef SyncJobPollCallback = void Function(SyncJobStatusResponse status);

Future<SyncLocalFilesResponse> syncLocalFilesV2(
  List<File> files, {
  UploadProgressCallback? onUploadProgress,
  SyncJobPollCallback? onPollProgress,
  String? conversationId,
}) async {
  try {
    // Step 1: Submit files
    var url = '${Env.apiBaseUrl}v2/sync-local-files';
    if (conversationId != null) {
      url += '?conversation_id=${Uri.encodeQueryComponent(conversationId)}';
    }
    var response = await makeMultipartApiCall(url: url, files: files, onUploadProgress: onUploadProgress);

    // Fast-path responses (no async job created)
    if (response.statusCode == 200) {
      return SyncLocalFilesResponse.fromJson(jsonDecode(response.body));
    }

    if (response.statusCode != 202) {
      if (response.statusCode == 400) {
        throw Exception('Audio file could not be processed by server');
      } else if (response.statusCode == 413) {
        throw Exception('Audio file is too large to upload');
      } else if (response.statusCode == 429) {
        throw Exception('Rate limited or budget exhausted');
      } else if (response.statusCode >= 500) {
        throw Exception('Server is temporarily unavailable');
      } else {
        throw Exception('Upload failed unexpectedly');
      }
    }

    // Step 2: Poll for completion
    var startResponse = SyncJobStartResponse.fromJson(jsonDecode(response.body));
    var jobId = startResponse.jobId;
    var pollInterval = Duration(milliseconds: startResponse.pollAfterMs);

    const maxPolls = 120; // 120 x 3s = 6 minutes max
    for (var i = 0; i < maxPolls; i++) {
      await Future.delayed(pollInterval);

      var pollResponse = await makeApiCall(
        url: '${Env.apiBaseUrl}v2/sync-local-files/$jobId',
        headers: {},
        method: 'GET',
        body: '',
      );

      if (pollResponse == null) {
        Logger.debug('syncLocalFilesV2 poll failed: null response');
        continue; // Retry on transient errors
      }

      // Terminal errors — don't retry
      if (pollResponse.statusCode == 404) {
        throw Exception('Sync job not found or expired');
      }
      if (pollResponse.statusCode == 403) {
        throw Exception('Not authorized to view this sync job');
      }
      if (pollResponse.statusCode != 200) {
        Logger.debug('syncLocalFilesV2 poll failed: ${pollResponse.statusCode}');
        continue; // Retry on transient errors
      }

      var jobStatus = SyncJobStatusResponse.fromJson(jsonDecode(pollResponse.body));

      // Report poll progress to caller for UI updates
      onPollProgress?.call(jobStatus);

      if (jobStatus.isTerminal) {
        // All segments failed → throw to match v1's 500 behavior (WAL stays retryable)
        if (jobStatus.status == 'failed') {
          throw Exception(jobStatus.error ?? 'Sync job failed');
        }
        // Success or partial failure → return result
        if (jobStatus.result != null) {
          return jobStatus.result!;
        }
        return SyncLocalFilesResponse(
          newConversationIds: [],
          updatedConversationIds: [],
          failedSegments: jobStatus.failedSegments,
          totalSegments: jobStatus.totalSegments,
        );
      }
    }

    // Polling timed out — don't mark as synced
    throw Exception('Sync job timed out waiting for results');
  } catch (e) {
    Logger.debug('syncLocalFilesV2 error: $e');
    rethrow;
  }
}

Future<(List<ServerConversation>, int, int)> searchConversationsServer(
  String query, {
  int? page,
  int? limit,
  bool includeDiscarded = true,
}) async {
  Logger.debug(Env.apiBaseUrl);
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/search',
    headers: {},
    method: 'POST',
    body: jsonEncode({
      'query': query,
      'page': page ?? 1,
      'per_page': limit ?? 10,
      'include_discarded': includeDiscarded,
    }),
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

Future<String> testConversationPrompt(String prompt, String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/test-prompt',
    headers: {},
    method: 'POST',
    body: jsonEncode({'prompt': prompt}),
  );
  if (response == null) return '';
  if (response.statusCode == 200) {
    return jsonDecode(response.body)['summary'];
  } else {
    return '';
  }
}

// *********************************
// ******** ACTION ITEMS ***********
// *********************************

Future<ActionItemsResponse> getActionItems({
  int limit = 50,
  int offset = 0,
  bool includeCompleted = true,
  DateTime? startDate,
  DateTime? endDate,
}) async {
  String url = '${Env.apiBaseUrl}v1/action-items?limit=$limit&offset=$offset&include_completed=$includeCompleted';

  if (startDate != null) {
    url += '&start_date=${startDate.toIso8601String()}';
  }
  if (endDate != null) {
    url += '&end_date=${endDate.toIso8601String()}';
  }

  var response = await makeApiCall(url: url, headers: {}, method: 'GET', body: '');

  if (response == null) return ActionItemsResponse(actionItems: [], hasMore: false);

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return ActionItemsResponse.fromJson(jsonDecode(body));
  } else {
    Logger.debug('getActionItems error ${response.statusCode}');
    return ActionItemsResponse(actionItems: [], hasMore: false);
  }
}

Future<List<App>> getConversationSuggestedApps(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/suggested-apps',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return [];
  Logger.debug('getConversationSuggestedApps: ${response.body}');
  if (response.statusCode == 200) {
    var data = jsonDecode(response.body);
    return (data['suggested_apps'] as List<dynamic>).map((appData) => App.fromJson(appData)).toList();
  }
  return [];
}

// *********************************
// ******** MERGE CONVERSATIONS ****
// *********************************

/// Response from the merge conversations API
class MergeConversationsResponse {
  final String status;
  final String message;
  final String? warning;
  final List<String> conversationIds;

  MergeConversationsResponse({
    required this.status,
    required this.message,
    this.warning,
    required this.conversationIds,
  });

  factory MergeConversationsResponse.fromJson(Map<String, dynamic> json) {
    return MergeConversationsResponse(
      status: json['status'] ?? 'merging',
      message: json['message'] ?? 'Merge started',
      warning: json['warning'],
      conversationIds: List<String>.from(json['conversation_ids'] ?? []),
    );
  }
}

/// Initiate merging of multiple conversations
Future<MergeConversationsResponse?> mergeConversations(List<String> conversationIds, {bool reprocess = true}) async {
  if (conversationIds.length < 2) {
    Logger.debug('mergeConversations: At least 2 conversations required');
    return null;
  }

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/merge',
    headers: {},
    method: 'POST',
    body: jsonEncode({'conversation_ids': conversationIds, 'reprocess': reprocess}),
  );

  if (response == null) return null;

  Logger.debug('mergeConversations: ${response.body}');

  if (response.statusCode == 200) {
    return MergeConversationsResponse.fromJson(jsonDecode(response.body));
  } else {
    Logger.debug('mergeConversations error: ${response.statusCode} - ${response.body}');
    return null;
  }
}
