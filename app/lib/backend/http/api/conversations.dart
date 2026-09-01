import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as action_items_wire;
import 'package:omi/backend/schema/gen/apps_wire.g.dart' as apps_wire;
import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Whether a non-200 response from POST /v1/conversations (process in-progress
/// conversation) is a benign race rather than a failure worth crash-reporting.
///
/// The backend returns 404 when there is no in-progress conversation to
/// process — which happens when the WS auto-finalize path already consumed the
/// in-progress conversation and cleared its Redis pointer before this
/// client-initiated create ran. Nothing to recover; the conversation is
/// already finalized. Reporting it floods crash reporting with noise.
bool isBenignInProgressConversationCreateStatus(int statusCode) => statusCode == 404;

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
    return CreateConversationResponse.fromGeneratedWireJson(jsonDecode(response.body) as Map<String, dynamic>);
  } else if (isBenignInProgressConversationCreateStatus(response.statusCode)) {
    Logger.debug('processInProgressConversation: no in-progress conversation (already finalized), skipping');
  } else {
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
  final result = await getConversationsResult(
    limit: limit,
    offset: offset,
    statuses: statuses,
    includeDiscarded: includeDiscarded,
    startDate: startDate,
    endDate: endDate,
    folderId: folderId,
    starred: starred,
  );
  return result.items;
}

// Same as [getConversations] but reports whether the request actually
// succeeded. An empty `items` with `ok == false` means the fetch failed
// (no response / non-200, e.g. auth token not ready right after a cold
// start) — which callers must NOT treat as "the user has no conversations".
Future<({List<ServerConversation> items, bool ok, bool truncated})> getConversationsResult({
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
  if (response == null) return (items: <ServerConversation>[], ok: false, truncated: false);
  if (response.statusCode == 200) {
    // decode body bytes to utf8 string and then parse json so as to avoid utf8 char issues
    var body = utf8.decode(response.bodyBytes);
    var memories = (jsonDecode(body) as List<dynamic>)
        .map((conversation) => ServerConversation.fromJson(conversation as Map<String, dynamic>))
        .toList();
    Logger.debug('getConversations length: ${memories.length}');
    return (items: memories, ok: true, truncated: isOmiListTruncated(response));
  }
  Logger.debug('getConversations error ${response.statusCode}');
  return (items: <ServerConversation>[], ok: false, truncated: false);
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
    return ServerConversation.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
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

Future<bool> unlinkCalendarEvent(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/calendar-event',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  return response.statusCode == 200;
}

/// Link a specific Google Calendar event to a conversation.
/// Returns the linked CalendarEventLink if successful, null otherwise.
Future<CalendarEventLink?> linkCalendarEvent(String conversationId, String eventId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/calendar-event',
    headers: {},
    method: 'POST',
    body: jsonEncode({'event_id': eventId}),
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    return CalendarEventLink.fromGenerated(
      wire.GeneratedCalendarEventLink.fromJson(jsonDecode(response.body) as Map<String, dynamic>),
    );
  }
  debugPrint('linkCalendarEvent error: ${response.statusCode} - ${response.body}');
  return null;
}

/// Auto-link a conversation to the best overlapping Google Calendar event.
/// Returns the linked CalendarEventLink if found, null otherwise.
Future<CalendarEventLink?> autoLinkCalendarEvent(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/calendar-event/auto-link',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    return CalendarEventLink.fromGenerated(
      wire.GeneratedCalendarEventLink.fromJson(jsonDecode(response.body) as Map<String, dynamic>),
    );
  }
  // 404 means no overlapping event found - not an error, just no match
  if (response.statusCode == 404) {
    debugPrint('autoLinkCalendarEvent: No overlapping calendar event found');
    return null;
  }
  debugPrint('autoLinkCalendarEvent error: ${response.statusCode} - ${response.body}');
  return null;
}

/// List Google Calendar events within a time range for the event picker.
/// Returns a list of CalendarEventLink objects, or empty list on error.
Future<List<CalendarEventLink>> listGoogleCalendarEvents({
  DateTime? timeMin,
  DateTime? timeMax,
  String? query,
  int maxResults = 20,
}) async {
  String url = '${Env.apiBaseUrl}v1/calendar/google/events?max_results=$maxResults';

  if (timeMin != null) {
    url += '&time_min=${timeMin.toUtc().toIso8601String()}';
  }
  if (timeMax != null) {
    url += '&time_max=${timeMax.toUtc().toIso8601String()}';
  }
  if (query != null && query.isNotEmpty) {
    url += '&q=${Uri.encodeComponent(query)}';
  }

  var response = await makeApiCall(url: url, headers: {}, method: 'GET', body: '');
  if (response == null) return [];
  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return (jsonDecode(body) as List<dynamic>)
        .map(
          (event) =>
              CalendarEventLink.fromGenerated(wire.GeneratedCalendarEventLink.fromJson(event as Map<String, dynamic>)),
        )
        .toList();
  }
  debugPrint('listGoogleCalendarEvents error: ${response.statusCode} - ${response.body}');
  return [];
}

/// Fetch calendar events in [start, end] that have no recorded conversation.
/// Returns capture-gap rows (never conversations), or an empty list on error.
Future<List<CalendarCaptureGap>> getCalendarCaptureGaps({
  required DateTime start,
  required DateTime end,
}) async {
  final url =
      '${Env.apiBaseUrl}v1/calendar/capture-gaps?start=${start.toUtc().toIso8601String()}&end=${end.toUtc().toIso8601String()}';
  var response = await makeApiCall(url: url, headers: {}, method: 'GET', body: '');
  if (response == null) return [];
  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return (jsonDecode(body) as List<dynamic>)
        .map(
          (row) => CalendarCaptureGap.fromGenerated(
            wire.GeneratedCalendarCaptureGap.fromJson(row as Map<String, dynamic>),
          ),
        )
        .toList();
  }
  // 400 means no connected calendar — nothing was captured, so nothing to show.
  debugPrint('getCalendarCaptureGaps: ${response.statusCode} - ${response.body}');
  return [];
}

Future<({ServerConversation? item, bool ok})> getConversationByIdResult(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return (item: null, ok: false);
  if (response.statusCode == 200) {
    return (item: ServerConversation.fromJson(jsonDecode(response.body) as Map<String, dynamic>), ok: true);
  } else if (response.statusCode == 402) {
    // Locked conversations are still returned by the list endpoint as a
    // redacted completed row, but their detail endpoint intentionally returns
    // 402. Treat that response as an authoritative terminal result for
    // lifecycle reconciliation so a stale Processing card is cleared.
    Logger.debug('Conversation is locked/redacted: $conversationId');
    return (item: null, ok: true);
  } else if (response.statusCode == 404) {
    return (item: null, ok: true);
  }
  return (item: null, ok: false);
}

Future<ServerConversation?> getConversationById(String conversationId) async {
  return (await getConversationByIdResult(conversationId)).item;
}

/// Fetches conversation-lifetime photo bytes for storage-backed photos. Legacy
/// inline base64 photos continue to render without a network round trip.
Future<Uint8List?> getConversationPhotoImage(String conversationId, String photoId) async {
  final response = await makeApiCall(
    url:
        '${Env.apiBaseUrl}v1/conversations/${Uri.encodeComponent(conversationId)}/photos/${Uri.encodeComponent(photoId)}/image',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response?.statusCode != 200) return null;
  return response!.bodyBytes;
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

Future<bool> updateConversationSummary(String conversationId, String? appId, String content) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/summary',
    headers: {'Content-Type': 'application/json'},
    method: 'PATCH',
    body: jsonEncode({'app_id': appId, 'content': content}),
  );
  if (response == null) return false;
  return response.statusCode == 200;
}

class TranscriptsResponse {
  List<TranscriptSegment> deepgram;
  List<TranscriptSegment> soniox;
  List<TranscriptSegment> whisperx;
  List<TranscriptSegment> speechmatics;
  List<TranscriptSegment> prerecorded;

  TranscriptsResponse({
    this.deepgram = const [],
    this.soniox = const [],
    this.whisperx = const [],
    this.speechmatics = const [],
    this.prerecorded = const [],
  });

  factory TranscriptsResponse.fromJson(Map<String, dynamic> json) {
    return TranscriptsResponse.fromGeneratedWireJson(json);
  }

  factory TranscriptsResponse.fromGeneratedWireJson(Map<String, dynamic> json) {
    List<TranscriptSegment> readSegments(String key) {
      final segments = json[key];
      if (segments is! List) return [];
      return segments
          .map(
            (segment) => TranscriptSegment.fromGenerated(
              wire.GeneratedTranscriptSegment.fromJson(segment as Map<String, dynamic>),
            ),
          )
          .toList();
    }

    return TranscriptsResponse(
      deepgram: readSegments('deepgram'),
      soniox: readSegments('soniox'),
      whisperx: readSegments('whisperx'),
      speechmatics: readSegments('speechmatics'),
      prerecorded: readSegments('prerecorded'),
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
    return TranscriptsResponse.fromGeneratedWireJson(jsonDecode(response.body) as Map<String, dynamic>);
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

/// Outcome of an upload-only POST to /v2/sync-local-files.
/// Exactly one of [jobId] (HTTP 202 — audio received, processing in the
/// background; reconcile later) or [completed] (HTTP 200 fast-path — server
/// already returned the result synchronously) is non-null.
class UploadFilesResult {
  final String? jobId;
  final SyncLocalFilesResponse? completed;

  const UploadFilesResult._(this.jobId, this.completed);
  factory UploadFilesResult.queued(String jobId) => UploadFilesResult._(jobId, null);
  factory UploadFilesResult.done(SyncLocalFilesResponse result) => UploadFilesResult._(null, result);

  bool get isQueued => jobId != null;
}

class SyncUploadHttpException implements Exception {
  final int statusCode;
  final String message;

  const SyncUploadHttpException(this.statusCode, this.message);

  @override
  String toString() => 'SyncUploadHttpException(status=$statusCode): $message';
}

/// Server-provided classification for a sync upload HTTP 429.
///
/// Fair use is deliberately opt-in: an unknown, proxy-generated, or platform
/// 429 is backend capacity unless the response carries Omi's explicit reason.
enum SyncRateLimitKind { fairUse, backendCapacity }

@visibleForTesting
bool shouldRequestSyncCaptureManifest(String? conversationId, bool claimLiveCapture) =>
    conversationId != null && claimLiveCapture;

Future<String?> _createSyncCaptureManifest(List<File> files, String conversationId) async {
  final claims = <Map<String, String>>[];
  for (final file in files) {
    final digest = await sha256.bind(file.openRead()).first;
    claims.add({'name': file.uri.pathSegments.last, 'sha256': digest.toString()});
  }
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/sync-capture-manifest',
    headers: const {},
    body: jsonEncode(
      wire.GeneratedSyncCaptureManifestRequest(
        conversationId: conversationId,
        files: [
          for (final claim in claims)
            wire.GeneratedSyncCaptureManifestFile(name: claim['name']!, sha256: claim['sha256']!),
        ],
      ).toJson(),
    ),
    method: 'POST',
  );
  if (response?.statusCode != 200) return null;
  final body = wire.GeneratedSyncCaptureManifestResponse.fromJson(jsonDecode(response!.body) as Map<String, dynamic>);
  return body.manifest;
}

/// Thrown when a sync upload is rate-limited (HTTP 429).
/// [retryAfterSeconds] is the server's Retry-After when provided.
class SyncRateLimitedException implements Exception {
  final SyncRateLimitKind kind;
  final int? retryAfterSeconds;
  SyncRateLimitedException({required this.kind, this.retryAfterSeconds});

  @override
  String toString() => 'SyncRateLimitedException(kind=$kind, retryAfter=$retryAfterSeconds)';
}

/// Thrown when the server permanently refuses a recording because its capture
/// time is older than the automatic-recovery window (HTTP 422
/// `backfill_lookback_exceeded`). No amount of retrying can make this upload
/// succeed, so callers must stop re-offering the file instead of spending the
/// recording's retry budget on it.
class SyncRecoveryWindowExceededException implements Exception {
  const SyncRecoveryWindowExceededException();

  @override
  String toString() => 'SyncRecoveryWindowExceededException()';
}

/// Classifies a sync 422 as the backend's terminal lookback rejection.
///
/// Keyed on the bounded `code` the sync routes emit, never on human-readable
/// detail text: any other 422 stays a generic retryable failure.
@visibleForTesting
bool isSyncRecoveryWindowExceededResponse(http.Response response) {
  if (response.statusCode != 422) return false;
  try {
    final body = wire.GeneratedSyncRecoveryWindowExceededResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    return body.code == 'backfill_lookback_exceeded';
  } catch (_) {
    return false;
  }
}

/// A synchronous upload response that durably reached the server but did not
/// transcribe every segment. Callers keep the local WAL and retry it; the
/// backend deduplicates any segments that already succeeded.
class SyncUploadIncompleteException implements Exception {
  final int failedSegments;

  const SyncUploadIncompleteException(this.failedSegments);

  @override
  String toString() => 'SyncUploadIncompleteException(failedSegments=$failedSegments)';
}

@visibleForTesting
SyncLocalFilesResponse requireCompleteSyncUpload(SyncLocalFilesResponse response) {
  if (response.hasPartialFailure) {
    throw SyncUploadIncompleteException(response.failedSegments);
  }
  return response;
}

/// Parse a Retry-After header expressed in delta-seconds. Returns null for an
/// absent or non-integer (HTTP-date) value; the caller falls back to a default.
int? _parseRetryAfterSeconds(http.Response response) {
  final raw = response.headers['retry-after'];
  if (raw == null) return null;
  return int.tryParse(raw.trim());
}

/// Classifies a sync 429 without relying on human-readable error text.
///
/// The application-generated restriction response carries this bounded header.
/// Everything else remains a generic backend-capacity limit.
SyncRateLimitKind syncRateLimitKindForResponse(http.Response response) {
  final reason = response.headers['x-omi-rate-limit-reason']?.trim().toLowerCase();
  return reason == 'fair_use' ? SyncRateLimitKind.fairUse : SyncRateLimitKind.backendCapacity;
}

/// Upload-only: POST files and return as soon as the server acknowledges
/// (HTTP 202 with a job_id, or the 200 fast-path with a finished result).
/// Does NOT wait for server-side processing — the caller marks the WAL
/// `uploaded` and a reconciler resolves [jobId] later via [fetchSyncJobStatus].
/// Error-status mapping matches the old polling path so callers' retry logic
/// is unchanged.
Future<UploadFilesResult> uploadLocalFilesV2(
  List<File> files, {
  UploadProgressCallback? onUploadProgress,
  String? conversationId,
  bool claimLiveCapture = false,
  Geolocation? geolocation,
}) async {
  String? captureManifest;
  if (shouldRequestSyncCaptureManifest(conversationId, claimLiveCapture)) {
    captureManifest = await _createSyncCaptureManifest(files, conversationId!);
  }
  var url = '${Env.apiBaseUrl}v2/sync-local-files';
  if (conversationId != null) {
    url += '?conversation_id=${Uri.encodeQueryComponent(conversationId)}';
  }
  var response = await makeMultipartApiCall(
    url: url,
    files: files,
    headers: {
      if (captureManifest != null) 'X-Omi-Sync-Capture-Manifest': captureManifest,
      if (geolocation != null) 'X-Omi-Conversation-Geolocation': jsonEncode(geolocation.toJson()),
    },
    onUploadProgress: onUploadProgress,
  );

  if (response.statusCode == 200) {
    // Fast-path: server processed synchronously and returned the result. A
    // legacy server can still encode partial work in a 200, which must follow
    // the retry path rather than acknowledging/deleting the local WAL.
    final completed = SyncLocalFilesResponse.fromGenerated(
      wire.GeneratedSyncLocalFilesResultResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>),
    );
    return UploadFilesResult.done(requireCompleteSyncUpload(completed));
  }
  if (response.statusCode == 202) {
    final start = SyncJobStartResponse.fromGenerated(
      wire.GeneratedSyncJobStartResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>),
    );
    if (start.jobId.isEmpty) {
      throw Exception('Upload accepted but no job id returned');
    }
    return UploadFilesResult.queued(start.jobId);
  }
  if (response.statusCode == 400) {
    throw SyncUploadHttpException(response.statusCode, 'Audio file could not be processed by server');
  } else if (response.statusCode == 401 || response.statusCode == 403) {
    throw SyncUploadHttpException(response.statusCode, 'Upload authentication failed');
  } else if (response.statusCode == 413) {
    throw SyncUploadHttpException(response.statusCode, 'Audio file is too large to upload');
  } else if (response.statusCode == 429 ||
      (response.statusCode == 503 &&
          response.headers['x-omi-rate-limit-reason']?.trim().toLowerCase() == 'backfill_capacity')) {
    throw SyncRateLimitedException(
      kind: syncRateLimitKindForResponse(response),
      retryAfterSeconds: _parseRetryAfterSeconds(response),
    );
  } else if (isSyncRecoveryWindowExceededResponse(response)) {
    throw const SyncRecoveryWindowExceededException();
  } else if (response.statusCode >= 500) {
    throw SyncUploadHttpException(response.statusCode, 'Server is temporarily unavailable');
  }
  throw SyncUploadHttpException(response.statusCode, 'Upload failed unexpectedly');
}

/// Why a single job-status fetch did not yield a usable status.
/// - [notFound]  : 404/403 — job expired, unknown, or not ours. Unrecoverable
///                 for this job_id; the caller must fall back to re-upload.
/// - [transient] : network/5xx/null — retry later, job may still be alive.
enum SyncJobFetchOutcome { ok, notFound, transient }

class SyncJobFetch {
  final SyncJobFetchOutcome outcome;
  final SyncJobStatusResponse? status;
  const SyncJobFetch(this.outcome, [this.status]);
}

/// Single GET of a sync job's status — no polling loop. The reconciler owns
/// the polling cadence and decides what to do per [SyncJobFetchOutcome].
Future<SyncJobFetch> fetchSyncJobStatus(String jobId) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/sync-local-files/$jobId',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) {
    DebugLogManager.logEvent('fetch_sync_job_status', {'jobId': jobId, 'httpStatus': null, 'outcome': 'transient'});
    return const SyncJobFetch(SyncJobFetchOutcome.transient);
  }
  if (response.statusCode == 404 || response.statusCode == 403) {
    DebugLogManager.logEvent('fetch_sync_job_status', {
      'jobId': jobId,
      'httpStatus': response.statusCode,
      'outcome': 'notFound',
    });
    return const SyncJobFetch(SyncJobFetchOutcome.notFound);
  }
  if (response.statusCode != 200) {
    DebugLogManager.logEvent('fetch_sync_job_status', {
      'jobId': jobId,
      'httpStatus': response.statusCode,
      'outcome': 'transient',
    });
    return const SyncJobFetch(SyncJobFetchOutcome.transient);
  }
  try {
    return SyncJobFetch(
      SyncJobFetchOutcome.ok,
      SyncJobStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>),
    );
  } catch (e) {
    Logger.debug('fetchSyncJobStatus parse error: $e');
    return const SyncJobFetch(SyncJobFetchOutcome.transient);
  }
}

/// Serialize a local calendar-day bound for conversation search.
///
/// Local [DateTime] values have no offset in [DateTime.toIso8601String], and
/// `search_conversations_endpoint` parses naive datetimes in the server TZ.
/// Convert to UTC first, matching the conversation-list date filter.
String serializeConversationSearchDateBound(DateTime date) => date.toUtc().toIso8601String();

Future<(List<ServerConversation>, int, int)> searchConversationsServer(
  String query, {
  int? page,
  int? limit,
  bool includeDiscarded = true,
  DateTime? startDate,
  DateTime? endDate,
  String? speakerId,
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
      if (startDate != null) 'start_date': serializeConversationSearchDateBound(startDate),
      if (endDate != null) 'end_date': serializeConversationSearchDateBound(endDate),
      if (speakerId != null) 'speaker_id': speakerId,
    }),
  );
  if (response == null) return (<ServerConversation>[], 0, 0);
  if (response.statusCode == 200) {
    final data = wire.GeneratedSearchConversationsResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    // Search items are ConversationSearchItem (includes match_snippets); parse via JSON so
    // ServerConversation keeps seek-to-moment evidence without widening GeneratedConversation.
    final convos = data.items.map((conversation) => ServerConversation.fromJson(conversation.toJson())).toList();
    return (convos, data.currentPage, data.totalPages);
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
    return wire.GeneratedConversationTestPromptResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).summary;
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

  if (response == null) return const ActionItemsResponse(actionItems: [], hasMore: false);

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return action_items_wire.GeneratedActionItemsResponse.fromJson(jsonDecode(body) as Map<String, dynamic>);
  } else {
    Logger.debug('getActionItems error ${response.statusCode}');
    return const ActionItemsResponse(actionItems: [], hasMore: false);
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
    final data = apps_wire.GeneratedConversationSuggestedAppsResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    return data.suggestedApps.map(App.fromGeneratedDetail).toList();
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
    return MergeConversationsResponse.fromGenerated(wire.GeneratedMergeConversationsResponse.fromJson(json));
  }

  factory MergeConversationsResponse.fromGenerated(wire.GeneratedMergeConversationsResponse generated) {
    return MergeConversationsResponse(
      status: generated.status,
      message: generated.message,
      warning: generated.warning,
      conversationIds: generated.conversationIds,
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
    return MergeConversationsResponse.fromGenerated(
      wire.GeneratedMergeConversationsResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>),
    );
  } else {
    Logger.debug('mergeConversations error: ${response.statusCode} - ${response.body}');
    return null;
  }
}
