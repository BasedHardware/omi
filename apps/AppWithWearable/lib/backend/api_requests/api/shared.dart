import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:instabug_http_client/instabug_http_client.dart';

Future<http.Response?> makeApiCall({
  required String url,
  required Map<String, String> headers,
  required String body,
  required String method,
}) async {
  try {
    final client = InstabugHttpClient();

    if (method == 'POST') {
      return await client.post(Uri.parse(url), headers: headers, body: body);
    } else if (method == 'GET') {
      return await client.get(Uri.parse(url), headers: headers);
    } else if (method == 'DELETE') {
      return await client.delete(Uri.parse(url), headers: headers);
    }
  } catch (e) {
    debugPrint('HTTP request failed: $e');
    return null;
  } finally {}
  return null;
}

// Function to extract content from the API response.
dynamic extractContentFromResponse(http.Response? response,
    {bool isEmbedding = false, bool isFunctionCalling = false}) {
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
    throw Exception('Error fetching data: ${response?.statusCode}');
    // return {'error': response?.statusCode};
  }
}
