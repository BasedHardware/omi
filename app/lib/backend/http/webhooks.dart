import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';

Future<String> webhookOnMemoryCreatedCall(ServerMemory? memory, {bool returnRawBody = false}) async {
  if (memory == null) return '';
  debugPrint('devModeWebhookCall: $memory');
  String url = SharedPreferencesUtil().webhookOnMemoryCreated;
  if (url.isEmpty) return '';
  if (url.contains('?')) {
    url += '&uid=${SharedPreferencesUtil().uid}';
  } else {
    url += '?uid=${SharedPreferencesUtil().uid}';
  }
  debugPrint('triggerMemoryRequestAtEndpoint: $url');
  var data = memory.toJson();
  try {
    var response = await makeApiCall(
      url: url,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(data),
      method: 'POST',
    );
    debugPrint('response: ${response?.statusCode}');
    if (returnRawBody) return jsonEncode({'statusCode': response?.statusCode, 'body': response?.body});
    var body = jsonDecode(response?.body ?? '{}');
    return body['message'] ?? '';
  } on FormatException catch (e) {
    debugPrint('Response not a valid json: $e');
    return '';
  } catch (e) {
    debugPrint('Error triggering memory request at endpoint: $e');
    return '';
  }
}
