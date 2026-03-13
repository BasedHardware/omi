import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/e2ee_middleware.dart';
import 'package:omi/utils/logger.dart';

Future<Memory?> createMemoryServer(String content, String visibility, String category) async {
  // Encrypt content client-side if E2EE is enabled
  final encryptedContent = await E2eeMiddleware.encryptIfEnabled(content);

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories',
    headers: {},
    method: 'POST',
    body: json.encode({
      'content': encryptedContent,
      'visibility': visibility,
      'category': category,
    }),
  );
  if (response == null) return null;
  Logger.debug('createMemory response: ${response.body}');
  if (response.statusCode == 200) {
    var memory = Memory.fromJson(json.decode(response.body));
    // Decrypt content after reading back from server
    memory.content = await E2eeMiddleware.decryptIfEnabled(memory.content);
    return memory;
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

Future<List<Memory>> getMemories({int limit = 100, int offset = 0}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/memories?limit=$limit&offset=$offset',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    if (decoded is List) {
      var memories = decoded.map((e) => Memory.fromJson(e)).toList();
      // Decrypt content fields if E2EE is enabled
      if (E2eeMiddleware.isE2eeEnabled()) {
        for (var memory in memories) {
          memory.content = await E2eeMiddleware.decryptIfEnabled(memory.content);
        }
      }
      return memories;
    }
  }
  return [];
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
