import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/shared.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/server/memory.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

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
  // data['recordingFileBase64'] = await wavToBase64(memory.recordingFilePath ?? '');
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
    print(body);
    return body['message'] ?? '';
  } catch (e) {
    debugPrint('Error triggering memory request at endpoint: $e');
    // TODO: is it bad for reporting?  I imagine most of the time is backend error, so nah.
    CrashReporting.reportHandledCrash(e, StackTrace.current, level: NonFatalExceptionLevel.info, userAttributes: {
      'url': url,
    });
    return '';
  }
}

Future<String> webhookOnTranscriptReceivedCall(List<TranscriptSegment> segments, String sessionId) async {
  debugPrint('webhookOnTranscriptReceivedCall: $segments');
  return triggerTranscriptSegmentsRequest(SharedPreferencesUtil().webhookOnTranscriptReceived, sessionId, segments);
}

Future<String> getPluginMarkdown(String pluginMarkdownPath) async {
  // https://raw.githubusercontent.com/BasedHardware/Friend/main/assets/external_plugins_instructions/notion-conversations-crm.md
  var response = await makeApiCall(
    url: 'https://raw.githubusercontent.com/BasedHardware/Friend/main$pluginMarkdownPath',
    method: 'GET',
    headers: {},
    body: '',
  );
  return response?.body ?? '';
}

Future<bool> isPluginSetupCompleted(String? url) async {
  if (url == null || url.isEmpty) return true;
  var response = await makeApiCall(
    url: '$url?uid=${SharedPreferencesUtil().uid}',
    method: 'GET',
    headers: {},
    body: '',
  );
  var data = jsonDecode(response?.body ?? '{}');
  print(data);
  return data['is_setup_completed'] ?? false;
}

Future<String> triggerTranscriptSegmentsRequest(String url, String sessionId, List<TranscriptSegment> segments) async {
  debugPrint('triggerMemoryRequestAtEndpoint: $url');
  if (url.isEmpty) return '';
  if (url.contains('?')) {
    url += '&uid=${SharedPreferencesUtil().uid}';
  } else {
    url += '?uid=${SharedPreferencesUtil().uid}';
  }
  try {
    var response = await makeApiCall(
      url: url,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'session_id': sessionId,
        'segments': segments.map((e) => e.toJson()).toList(),
      }),
      method: 'POST',
    );
    debugPrint('response: ${response?.statusCode}');
    var body = jsonDecode(response?.body ?? '{}');
    print(body);
    return body['message'] ?? '';
  } catch (e) {
    debugPrint('Error triggering transcript request at endpoint: $e');
    // TODO: is it bad for reporting?  I imagine most of the time is backend error, so nah.
    CrashReporting.reportHandledCrash(e, StackTrace.current, level: NonFatalExceptionLevel.info, userAttributes: {
      'url': url,
    });
    return '';
  }
}

Future<String?> wavToBase64(String filePath) async {
  if (filePath.isEmpty) return null;
  try {
    // Read file as bytes
    File file = File(filePath);
    if (!file.existsSync()) {
      // print('File does not exist: $filePath');
      return null;
    }
    List<int> fileBytes = await file.readAsBytes();

    // Encode bytes to base64
    String base64Encoded = base64Encode(fileBytes);

    return base64Encoded;
  } catch (e) {
    // print('Error converting WAV to base64: $e');
    return null; // Handle error gracefully in your application
  }
}
