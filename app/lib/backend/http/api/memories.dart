import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/read_retry.dart';
import 'package:omi/backend/schema/gen/memories_wire.g.dart' as wire;
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

Future<Memory?> createMemoryServer(
  String content,
  String visibility,
  String category,
) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories',
    headers: {},
    method: 'POST',
    body: json.encode({
      'content': content,
      'visibility': visibility,
      'category': category,
    }),
  );
  if (response == null) return null;
  Logger.debug('createMemory response: ${response.body}');
  if (response.statusCode == 200) {
    return Memory.fromGeneratedWireJson(
      json.decode(response.body) as Map<String, dynamic>,
    );
  }
  return null;
}

Future<bool> updateMemoryVisibilityServer(
  String memoryId,
  String visibility,
) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories/$memoryId/visibility?value=$visibility',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('updateMemoryVisibility response: ${response.body}');
  return response.statusCode == 200;
}

/// Why a [GetMemoriesResult] is not a successful read.
enum MemoriesFetchFailureReason { noResponse, httpError, decodeError }

/// Result of [getMemories], carrying whether server-side device_scope was supported
/// and whether the response was a partial page due to request-budget exhaustion.
///
/// [ok] is true only for a decoded 200. An empty [memories] list with [ok] false
/// is a failed fetch, not "the account has no memories".
class GetMemoriesResult {
  final List<Memory> memories;
  final bool deviceScopeSupported;
  final bool truncated;
  final String? nextCursor;
  final int? statusCode;
  final MemoriesFetchFailureReason? failureReason;

  const GetMemoriesResult(
    this.memories,
    this.deviceScopeSupported, {
    this.truncated = false,
    this.nextCursor,
    this.statusCode,
    this.failureReason,
  });

  bool get ok => failureReason == null;
}

/// Maps a GET /v3/memories HTTP outcome onto [GetMemoriesResult].
///
/// The 400 + `thisDeviceOnly` legacy fallback lives in [getMemoriesResult]; this
/// helper never treats that as success. A missing response, any other non-200,
/// or a 200 that cannot be decoded is a failure. Failures keep
/// [GetMemoriesResult.deviceScopeSupported] true so a 503 cannot be mistaken
/// for "device_scope unsupported".
@visibleForTesting
GetMemoriesResult memoriesResultFromHttp({
  required int? statusCode,
  String? body,
  bool truncated = false,
  String? nextCursor,
}) {
  if (statusCode == null) {
    return const GetMemoriesResult(
      [],
      true,
      failureReason: MemoriesFetchFailureReason.noResponse,
    );
  }
  if (statusCode == 200) {
    try {
      return GetMemoriesResult(
        _decodeMemoriesResponse(body ?? ''),
        true,
        truncated: truncated,
        nextCursor: nextCursor,
        statusCode: 200,
      );
    } catch (_) {
      return const GetMemoriesResult(
        [],
        true,
        statusCode: 200,
        failureReason: MemoriesFetchFailureReason.decodeError,
      );
    }
  }
  return GetMemoriesResult(
    const [],
    true,
    statusCode: statusCode,
    failureReason: MemoriesFetchFailureReason.httpError,
  );
}

/// Builds the query used by GET /v3/memories.
///
/// The backend treats cursor and offset paging as separate protocols. Keeping
/// that distinction here prevents a continuation request from accidentally
/// sending the previous offset alongside its cursor.
@visibleForTesting
String buildMemoriesListUrl({
  required String baseUrl,
  int limit = 100,
  int offset = 0,
  String? cursor,
  bool thisDeviceOnly = false,
}) {
  final base = baseUrl.endsWith('/') ? baseUrl : '$baseUrl/';
  final query = <String, String>{'limit': '$limit'};
  if (cursor != null) {
    query['cursor'] = cursor;
  } else {
    query['offset'] = '$offset';
  }
  if (thisDeviceOnly) query['device_scope'] = 'current';
  return Uri.parse('${base}v3/memories').replace(queryParameters: query).toString();
}

/// Builds the owner history route. Offset is used for the initial page and a
/// server-issued cursor takes over only when the response supplies one.
@visibleForTesting
String buildLedgerHistoryUrl({
  required String baseUrl,
  int limit = 500,
  int offset = 0,
  String? cursor,
}) {
  final base = baseUrl.endsWith('/') ? baseUrl : '$baseUrl/';
  final query = <String, String>{'limit': '$limit'};
  if (cursor == null) {
    query['offset'] = '$offset';
  } else {
    query['cursor'] = cursor;
  }
  return Uri.parse('${base}v3/memories/ledger-history')
      .replace(
        queryParameters: query,
      )
      .toString();
}

@visibleForTesting
Future<void> reportMemoriesFetchFailure(
  GetMemoriesResult result, {
  Future<void> Function(String)? supportLog,
  void Function(Map<String, dynamic>)? productError,
  Future<void> Function(Object, StackTrace, {required Map<String, String> userAttributes})? nonFatal,
}) async {
  final message = 'Failed to fetch memories: status=${result.statusCode} reason=${result.failureReason?.name}';
  Logger.debug(message); // Avoid Talker's second Crashlytics event.
  try {
    await (supportLog ?? (message) => DebugLogManager.logError(message))(message);
  } catch (_) {
    // Support logging must not turn a handled fetch into an uncaught error.
  }
  final attributes = {
    'response_status_code': result.statusCode?.toString() ?? '',
    'failure_reason': result.failureReason?.name ?? '',
  };
  try {
    (productError ?? (properties) => AnalyticsManager().track('Product Error', properties: properties))({
      'error': message, // Bounded status/reason only, never response bodies or exception text.
      'error_kind': 'memories_fetch',
      'diagnostic_source': 'memories_fetch',
      ...attributes,
    });
  } catch (_) {
    // Analytics is supplemental to the primary non-fatal record.
  }
  if (result.failureReason == MemoriesFetchFailureReason.noResponse) return;
  await (nonFatal ?? PlatformManager.instance.crashReporter.reportNonFatal)(
    Exception(message),
    StackTrace.current,
    userAttributes: attributes,
  );
}

List<Memory> _decodeMemoriesResponse(String body) {
  return (json.decode(body) as List<dynamic>)
      .map(
        (memory) => Memory.fromGeneratedWireJson(
          Map<String, dynamic>.from(memory as Map),
        ),
      )
      .toList();
}

Future<GetMemoriesResult> getMemoriesResult({
  int limit = 100,
  int offset = 0,
  String? cursor,
  bool thisDeviceOnly = false,
  Future<http.Response?> Function(String url, Map<String, String> headers)? send,
  ReadRetry? retry,
  Future<void> Function(GetMemoriesResult)? reportFailure,
  DateTime? deadline,
}) async {
  final policy = retry ?? ReadRetry();
  final end = deadline ?? policy.now().add(ReadRetry.callerWindow);
  final url = buildMemoriesListUrl(
    baseUrl: Env.apiBaseUrl ?? '',
    limit: limit,
    offset: offset,
    cursor: cursor,
    thisDeviceOnly: thisDeviceOnly,
  );
  final report = reportFailure ?? reportMemoriesFetchFailure;
  http.Response? reportedResponse;
  final response = await policy.run(
    (timeout) => send != null
        ? send(url, const {})
        : makeApiCall(
            url: url,
            headers: const {},
            method: 'GET',
            body: '',
            retries: 0,
            timeout: timeout,
            canSend: () => !policy.isClosed && policy.now().isBefore(end)),
    deadline: end,
    onRetry: (response) async {
      reportedResponse = response;
      await report(memoriesResultFromHttp(statusCode: response.statusCode));
    },
  );
  // Legacy memory users cannot use server-side device_scope; fetch all and
  // signal that local device filtering should be skipped to avoid hiding
  // legacy rows that have no primary_capture_device/capture_device_ids.
  if (thisDeviceOnly && response != null && response.statusCode == 400) {
    final fallback = await getMemoriesResult(
      limit: limit,
      offset: offset,
      cursor: cursor,
      send: send,
      retry: policy,
      deadline: end,
      reportFailure: reportFailure,
    );
    return GetMemoriesResult(
      fallback.memories,
      false,
      truncated: fallback.truncated,
      nextCursor: fallback.nextCursor,
      statusCode: fallback.statusCode,
      failureReason: fallback.failureReason,
    );
  }
  if (response != null && response.statusCode != 200) {
    Logger.debug(
      'getMemories error ${response.statusCode}',
    );
  }
  final result = memoriesResultFromHttp(
    statusCode: response?.statusCode,
    body: response?.body,
    truncated: isOmiListTruncated(response),
    nextCursor: _nextMemoryCursor(response),
  );
  if (!result.ok && (response == null || !identical(response, reportedResponse))) {
    await report(result);
  }
  return result;
}

/// Convenience wrapper for callers that do not need the device_scope support flag.
Future<List<Memory>> getMemories({
  int limit = 100,
  int offset = 0,
  String? cursor,
  bool thisDeviceOnly = false,
}) async {
  final result = await getMemoriesResult(
    limit: limit,
    offset: offset,
    cursor: cursor,
    thisDeviceOnly: thisDeviceOnly,
  );
  return result.memories;
}

class GetLedgerHistoryResult {
  final List<Memory> memories;
  final bool supported;
  final bool truncated;
  final String? nextCursor;

  const GetLedgerHistoryResult(
    this.memories, {
    required this.supported,
    this.truncated = false,
    this.nextCursor,
  });
}

/// Fetch owner-scoped, non-current canonical ledger rows for review/history.
///
/// Older backends do not expose this additive route; any non-200 response is
/// therefore treated as an unavailable history projection while the current
/// memories list remains usable.
Future<GetLedgerHistoryResult> getLedgerHistory({
  int limit = 500,
  int offset = 0,
  String? cursor,
}) async {
  final response = await makeApiCall(
    url: buildLedgerHistoryUrl(
      baseUrl: Env.apiBaseUrl ?? '',
      limit: limit,
      offset: offset,
      cursor: cursor,
    ),
    headers: const {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200) {
    return const GetLedgerHistoryResult([], supported: false);
  }
  try {
    final result = GetLedgerHistoryResult(
      _decodeMemoriesResponse(response.body),
      supported: true,
      truncated: isOmiListTruncated(response),
      nextCursor: _nextMemoryCursor(response),
    );
    return result;
  } catch (error) {
    Logger.error('Failed to decode ledger history 200 response: $error');
    return const GetLedgerHistoryResult([], supported: false);
  }
}

String? _nextMemoryCursor(http.Response? response) {
  if (response == null) return null;
  for (final entry in response.headers.entries) {
    if (entry.key.toLowerCase() == 'x-omi-memory-next-cursor' && entry.value.isNotEmpty) {
      return entry.value;
    }
  }
  return null;
}

Future<bool> deleteMemoryServer(String memoryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories/$memoryId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('deleteMemory response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> deleteAllMemoriesServer() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('deleteAllMemories response: ${response.body}');
  return response.statusCode == 200;
}

class EditMemoryResult {
  final bool persisted;
  final Memory? authoritativeMemory;

  const EditMemoryResult({required this.persisted, this.authoritativeMemory});
}

class RevertMemoryResult {
  final bool persisted;
  final Memory? authoritativeMemory;

  const RevertMemoryResult({required this.persisted, this.authoritativeMemory});
}

/// Re-open one superseded canonical fact through backend ledger authority.
///
/// [operationId] is minted once by the provider for the user tap and remains
/// stable for this request. The response must carry the appended authoritative
/// replacement; callers must not infer success from the status code alone.
Future<RevertMemoryResult> revertMemoryServer(
  String memoryId,
  String operationId,
) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories/$memoryId/revert',
    headers: {},
    method: 'POST',
    body: json.encode(
      wire.GeneratedMemoryRevertRequest(operationId: operationId).toJson(),
    ),
  );
  if (response == null || response.statusCode != 200) {
    return const RevertMemoryResult(persisted: false);
  }
  try {
    final payload = wire.GeneratedMemoryEditResponse.fromJson(
      json.decode(response.body) as Map<String, dynamic>,
    );
    if (payload.status != 'ok') {
      return const RevertMemoryResult(persisted: false);
    }
    final authoritativeMemory = payload.memory == null ? null : Memory.fromGeneratedWireJson(payload.memory!.toJson());
    return RevertMemoryResult(
      persisted: authoritativeMemory != null,
      authoritativeMemory: authoritativeMemory,
    );
  } catch (error) {
    Logger.warning('revertMemory response decode failed: $error');
    return const RevertMemoryResult(persisted: false);
  }
}

Future<EditMemoryResult> editMemoryServer(String memoryId, String value) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories/$memoryId',
    headers: {},
    method: 'PATCH',
    body: json.encode({'value': value}),
  );
  if (response == null || response.statusCode != 200) {
    return const EditMemoryResult(persisted: false);
  }
  try {
    final payload = json.decode(response.body) as Map<String, dynamic>;
    final rawMemory = payload['memory'];
    final authoritativeMemory =
        rawMemory is Map ? Memory.fromGeneratedWireJson(Map<String, dynamic>.from(rawMemory)) : null;
    Logger.debug(
      'editMemory persisted; authoritativeReplacement=${authoritativeMemory != null}',
    );
    return EditMemoryResult(
      persisted: true,
      authoritativeMemory: authoritativeMemory,
    );
  } catch (error) {
    Logger.warning('editMemory response decode failed: $error');
    return const EditMemoryResult(persisted: false);
  }
}

Future<bool> updateMemoryBaselineServer(String memoryId, bool value) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories/$memoryId/baseline?value=$value',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('updateMemoryBaseline response: ${response.body}');
  return response.statusCode == 200;
}

/// Record an explicit user decision for a canonical memory/ledger row.
///
/// This uses the existing canonical review mutation rather than inventing a
/// client-side ledger authority. A negative decision removes the row from
/// prompt/search projections; a positive decision restores its review state.
Future<bool> reviewMemoryServer(String memoryId, bool value) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories/$memoryId/review?value=$value',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('reviewMemory response: ${response.body}');
  return response.statusCode == 200;
}
