import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:instabug_http_client/instabug_http_client.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';

Future<String> getAuthHeader() async {
  if (SharedPreferencesUtil().authToken == '') {
    SharedPreferencesUtil().authToken = await getIdToken() ?? '';
  }
  if (SharedPreferencesUtil().authToken == '') {
    throw Exception('No auth token found');
  }
  return 'Bearer ${SharedPreferencesUtil().authToken}';
}

Future<http.Response?> makeApiCall({
  required String url,
  required Map<String, String> headers,
  required String body,
  required String method,
}) async {
  try {
    // var startTime = DateTime.now();
    bool result = await InternetConnection().hasInternetAccess; // 600 ms on avg
    // debugPrint('Internet connection check took: ${DateTime.now().difference(startTime).inMilliseconds} ms');
    if (!result) {
      debugPrint('No internet connection, aborting $method $url');
      return null;
    }
    if (url.contains(Env.apiBaseUrl!)) {
      headers['Authorization'] = await getAuthHeader();
    }

    final client = InstabugHttpClient();

    if (method == 'POST') {
      return await client.post(Uri.parse(url), headers: headers, body: body);
    } else if (method == 'GET') {
      return await client.get(Uri.parse(url), headers: headers);
    } else if (method == 'DELETE') {
      return await client.delete(Uri.parse(url), headers: headers);
    } else {
      throw Exception('Unsupported HTTP method: $method');
    }
  } catch (e, stackTrace) {
    debugPrint('HTTP request failed: $e');
    CrashReporting.reportHandledCrash(
      e,
      stackTrace,
      userAttributes: {'url': url, 'method': method},
      level: NonFatalExceptionLevel.warning,
    );
    return null;
  } finally {}
}

// Function to extract content from the API response.
dynamic extractContentFromResponse(
  http.Response? response, {
  bool isEmbedding = false,
  bool isFunctionCalling = false,
}) {
  if (response != null && response.statusCode == 200) {
    var data = jsonDecode(response.body);
    if (isEmbedding) {
      var embedding = data['data'][0]['embedding'];
      return embedding;
    }
    var message = data['choices'][0]['message'];
    if (isFunctionCalling && message['tool_calls'] != null) {
      debugPrint('message $message');
      debugPrint('message ${message['tool_calls'].runtimeType}');
      return message['tool_calls'];
    }
    return data['choices'][0]['message']['content'];
  } else {
    debugPrint('Error fetching data: ${response?.statusCode}');
    // TODO: handle error, better specially for script migration
    CrashReporting.reportHandledCrash(
      Exception('Error fetching data: ${response?.statusCode}'),
      StackTrace.current,
      userAttributes: {
        'response_null': (response == null).toString(),
        'response_status_code': response?.statusCode.toString() ?? '',
        'is_embedding': isEmbedding.toString(),
        'is_function_calling': isFunctionCalling.toString(),
      },
      level: NonFatalExceptionLevel.warning,
    );
    return null;
  }
}
