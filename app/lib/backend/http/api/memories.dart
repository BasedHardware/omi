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
    return Memory.fromJson(json.decode(response.body));
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

/// Result of [getMemories], carrying whether server-side device_scope was supported.
class GetMemoriesResult {
  final List<Memory> memories;
  final bool deviceScopeSupported;

  const GetMemoriesResult(this.memories, this.deviceScopeSupported);
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
    var decoded = json.decode(response.body);
    if (decoded is List) {
      final memories = decoded.map((e) {
        final item = Map<String, dynamic>.from(e as Map);
        wire.GeneratedMemoryDB.fromJson(item);
        return Memory.fromJson(item);
      }).toList();
      return GetMemoriesResult(memories, true);
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

Future<bool> editMemoryServer(String memoryId, String value) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories/$memoryId?value=$value',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('editMemory response: ${response.body}');
  return response.statusCode == 200;
}
