import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:http/http.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:mime/mime.dart';

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
    //TODO: Some endpoints return an array. I guess it makes sense to have standardised response strcuture. What do you think? @josancamon19
    return body['message'] ?? '';
  } on FormatException catch (e) {
    debugPrint('Response not a valid json: $e');
    return '';
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
  // was called twice?
  if (segments.isEmpty || SharedPreferencesUtil().webhookOnTranscriptReceived.isEmpty) return '';
  debugPrint('webhookOnTranscriptReceivedCall: $segments');
  return triggerTranscriptSegmentsRequest(SharedPreferencesUtil().webhookOnTranscriptReceived, sessionId, segments);
}

Future<String> triggerTranscriptSegmentsRequest(String url, String sessionId, List<TranscriptSegment> segments) async {
  debugPrint('triggerMemoryRequestAtEndpoint: $url');
  if (url.isEmpty) return '';
  if (url.contains('?')) {
    url += '&uid=${SharedPreferencesUtil().uid}';
  } else {
    url += '?uid=${SharedPreferencesUtil().uid}';
  }
  Response? response;
  try {
    response = await makeApiCall(
      url: url,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'session_id': sessionId,
        'segments': segments.map((e) => e.toJson()).toList(),
      }),
      method: 'POST',
    );
    debugPrint('response: ${response?.statusCode}');
    if (response?.statusCode == 200) {
      var body = jsonDecode(response?.body ?? '{}');
      print(body);
      // TODO: Some endpoints return an array. I guess it makes sense to have standardised response structure.
      return body['message'] ?? '';
    } else {
      return '';
    }
  } on FormatException catch (e) {
    debugPrint('Response not a valid json: $e');
    // TODO: It is either a string or html string. So I guess we can return it as is.
    // I guess we should probably have a predefined response structure for webhooks which the webhook creators have to follow? @josancamon19
    return response?.body ?? '';
  } catch (e) {
    debugPrint('Error triggering transcript request at endpoint: $e');
    // TODO: is it bad for reporting?  I imagine most of the time is backend error, so nah.
    CrashReporting.reportHandledCrash(e, StackTrace.current, level: NonFatalExceptionLevel.info, userAttributes: {
      'url': url,
    });
    return '';
  }
}

Future<String?> wavToBase64Url(String filePath) async {
  print('wavToBase64Url: $filePath');
  if (filePath.isEmpty) return null;
  try {
    File file = File(filePath);
    if (!file.existsSync()) return null;
    List<int> fileBytes = await file.readAsBytes();
    String base64Encoded = base64Encode(fileBytes);
    String? mimeType = lookupMimeType(filePath) ?? 'application/octet-stream';
    return 'data:$mimeType;base64,$base64Encoded';
  } catch (e) {
    return null; // Handle error gracefully in your application
  }
}
