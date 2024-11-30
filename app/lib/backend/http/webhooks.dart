import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/conversation.dart';

Future<String> webhookOnConversationCreatedCall(ServerConversation? conversation, {bool returnRawBody = false}) async {
  if (conversation == null) return '';
  debugPrint('devModeWebhookCall: $conversation');
  String url = SharedPreferencesUtil().webhookOnConversationCreated;
  if (url.isEmpty) return '';
  if (url.contains('?')) {
    url += '&uid=${SharedPreferencesUtil().uid}';
  } else {
    url += '?uid=${SharedPreferencesUtil().uid}';
  }
  debugPrint('triggerMemoryRequestAtEndpoint: $url');
  var data = conversation.toJson();
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
    debugPrint('Error triggering conversation request at endpoint: $e');
    return '';
  }
}
