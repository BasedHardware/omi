import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/shared.dart';
import 'package:friend_private/backend/server/memory.dart';
import 'package:friend_private/env/env.dart';

Future<List<ServerMemory>> getMemories() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/memories', headers: {}, method: 'GET', body: '');
  if (response == null) return [];
  debugPrint('getMemories: ${response.body}');
  if (response.statusCode == 200) {
    var memories = (jsonDecode(response.body) as List<dynamic>).map((memory) => ServerMemory.fromJson(memory)).toList();
    debugPrint('getMemories length: ${memories.length}');
    return memories;
  }
  return [];
}
