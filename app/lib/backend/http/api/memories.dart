import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/env/env.dart';

Future<Memory?> createMemoryServer(String content, String visibility, String category) async {
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
  debugPrint('createMemory response: ${response.body}');
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
  debugPrint('updateMemoryVisibility response: ${response.body}');
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
      return decoded.map((e) => Memory.fromJson(e)).toList();
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
  debugPrint('deleteMemory response: ${response.body}');
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
  debugPrint('deleteAllMemories response: ${response.body}');
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
  debugPrint('editMemory response: ${response.body}');
  return response.statusCode == 200;
}
