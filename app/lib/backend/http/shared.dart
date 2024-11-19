import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:http/http.dart' as http;
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';

Future<String> getAuthHeader() async {
  DateTime? expiry = DateTime.fromMillisecondsSinceEpoch(SharedPreferencesUtil().tokenExpirationTime);
  bool hasAuthToken = SharedPreferencesUtil().authToken.isNotEmpty;

  bool isExpirationDateValid = !(expiry.isBefore(DateTime.now()) ||
      expiry.isAtSameMomentAs(DateTime.fromMillisecondsSinceEpoch(0)) ||
      (expiry.isBefore(DateTime.now().add(const Duration(minutes: 5))) && expiry.isAfter(DateTime.now())));

  if (SharedPreferencesUtil().customBackendUrl.isNotEmpty && (!hasAuthToken || !isExpirationDateValid)) {
    throw Exception('No auth token found');
  }

  if (!hasAuthToken || !isExpirationDateValid) {
    SharedPreferencesUtil().authToken = await getIdToken() ?? '';
  }

  if (!hasAuthToken) {
    if (isSignedIn()) {
      // should only throw if the user is signed in but the token is not found
      // if the user is not signed in, the token will always be empty
      throw Exception('No auth token found');
    }
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
      // headers['Authorization'] = ''; // set admin key + uid here for testing
    }

    final client = http.Client();

    http.Response? response = await _performRequest(client, url, headers, body, method);
    if (response.statusCode == 401) {
      Logger.log('Token expired on 1st attempt');
      // Refresh the token
      SharedPreferencesUtil().authToken = await getIdToken() ?? '';
      if (SharedPreferencesUtil().authToken.isNotEmpty) {
        // Update the header with the new token
        headers['Authorization'] = 'Bearer ${SharedPreferencesUtil().authToken}';
        // Retry the request with the new token
        response = await _performRequest(client, url, headers, body, method);
        Logger.log('Token refreshed and request retried');
        if (response.statusCode == 401) {
          // Force user to sign in again
          await signOut();
          Logger.handle(Exception('Authentication failed. Please sign in again.'), StackTrace.current,
              message: 'Authentication failed. Please sign in again.');
        }
      } else {
        // Force user to sign in again
        await signOut();
        Logger.handle(Exception('Authentication failed. Please sign in again.'), StackTrace.current,
            message: 'Authentication failed. Please sign in again.');
      }
    }

    return response;
  } catch (e, stackTrace) {
    debugPrint('HTTP request failed: $e, $stackTrace');
    CrashReporting.reportHandledCrash(
      e,
      stackTrace,
      userAttributes: {'url': url, 'method': method},
      level: NonFatalExceptionLevel.warning,
    );
    return null;
  } finally {}
}

Future<http.Response> _performRequest(
  http.Client client,
  String url,
  Map<String, String> headers,
  String body,
  String method,
) async {
  switch (method) {
    case 'POST':
      headers['Content-Type'] = 'application/json';
      return await client.post(Uri.parse(url), headers: headers, body: body);
    case 'GET':
      return await client.get(Uri.parse(url), headers: headers);
    case 'DELETE':
      headers['Content-Type'] = 'application/json';
      return await client.delete(Uri.parse(url), headers: headers, body: body);
    case 'PATCH':
      headers['Content-Type'] = 'application/json';
      return await client.patch(Uri.parse(url), headers: headers, body: body);
    default:
      throw Exception('Unsupported HTTP method: $method');
  }
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
