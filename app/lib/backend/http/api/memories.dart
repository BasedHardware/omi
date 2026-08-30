import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/memories_wire.g.dart' as wire;
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

Future<Memory?> createMemoryServer(String content, String visibility, String category) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories',
    headers: {},
    method: 'POST',
    body: json.encode({'content': content, 'visibility': visibility, 'category': category}),
  );
  if (response == null) return null;
  Logger.debug('createMemory response: ${response.body}');
  if (response.statusCode == 200) {
    return Memory.fromGeneratedWireJson(json.decode(response.body) as Map<String, dynamic>);
  }
  return null;
}

Future<bool> updateMemoryVisibilityServer(String memoryId, String visibility) async {
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

/// Result of [getMemories], carrying whether server-side device_scope was supported
/// and whether the response was a partial page due to request-budget exhaustion.
class GetMemoriesResult {
  final List<Memory> memories;
  final bool deviceScopeSupported;
  final bool truncated;

  const GetMemoriesResult(this.memories, this.deviceScopeSupported, {this.truncated = false});
}

List<Memory> _decodeMemoriesResponse(String body) {
  return (json.decode(body) as List<dynamic>)
      .map((memory) => Memory.fromGeneratedWireJson(Map<String, dynamic>.from(memory as Map)))
      .toList();
}

Future<GetMemoriesResult> getMemoriesResult({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
  var url = '${Env.apiBaseUrl}v3/memories?limit=$limit&offset=$offset';
  if (thisDeviceOnly) {
    url += '&device_scope=current';
  }
  var response = await makeApiCall(url: url, headers: {}, method: 'GET', body: '');
  if (response == null) {
    return GetMemoriesResult([], !thisDeviceOnly);
  }
  if (response.statusCode == 200) {
    try {
      return GetMemoriesResult(
        _decodeMemoriesResponse(response.body),
        true,
        truncated: isOmiListTruncated(response),
      );
    } catch (e) {
      Logger.error('Failed to decode memories 200 response: $e');
      return const GetMemoriesResult([], true);
    }
  }
  // Legacy memory users cannot use server-side device_scope; fetch all and
  // signal that local device filtering should be skipped to avoid hiding
  // legacy rows that have no primary_capture_device/capture_device_ids.
  if (thisDeviceOnly && response.statusCode == 400) {
    final fallback = await getMemoriesResult(limit: limit, offset: offset);
    return GetMemoriesResult(fallback.memories, false);
  }
  return GetMemoriesResult([], !thisDeviceOnly);
}

/// Convenience wrapper for callers that do not need the device_scope support flag.
Future<List<Memory>> getMemories({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
  final result = await getMemoriesResult(limit: limit, offset: offset, thisDeviceOnly: thisDeviceOnly);
  return result.memories;
}

class GetLedgerHistoryResult {
  final List<Memory> memories;
  final bool supported;
  final bool truncated;

  const GetLedgerHistoryResult(this.memories, {required this.supported, this.truncated = false});
}

/// Fetch owner-scoped, non-current canonical ledger rows for review/history.
///
/// Older backends do not expose this additive route; any non-200 response is
/// therefore treated as an unavailable history projection while the current
/// memories list remains usable.
Future<GetLedgerHistoryResult> getLedgerHistory({int limit = 500, int offset = 0}) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories/ledger-history?limit=$limit&offset=$offset',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200) {
    return const GetLedgerHistoryResult([], supported: false);
  }
  try {
    return GetLedgerHistoryResult(
      _decodeMemoriesResponse(response.body),
      supported: true,
      truncated: isOmiListTruncated(response),
    );
  } catch (error) {
    Logger.error('Failed to decode ledger history 200 response: $error');
    return const GetLedgerHistoryResult([], supported: false);
  }
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
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v3/memories', headers: {}, method: 'DELETE', body: '');
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
Future<RevertMemoryResult> revertMemoryServer(String memoryId, String operationId) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories/$memoryId/revert',
    headers: {},
    method: 'POST',
    body: json.encode(wire.GeneratedMemoryRevertRequest(operationId: operationId).toJson()),
  );
  if (response == null || response.statusCode != 200) {
    return const RevertMemoryResult(persisted: false);
  }
  try {
    final payload = wire.GeneratedMemoryEditResponse.fromJson(json.decode(response.body) as Map<String, dynamic>);
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
    Logger.debug('editMemory persisted; authoritativeReplacement=${authoritativeMemory != null}');
    return EditMemoryResult(persisted: true, authoritativeMemory: authoritativeMemory);
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
