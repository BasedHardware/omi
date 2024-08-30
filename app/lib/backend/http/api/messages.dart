import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/env/env.dart';

Future<List<ServerMessage>> getMessagesServer() async {
  // Construct the request URL
  final url = '${Env.apiBaseUrl}v1/messages';

  // Log the request details
  print('getMessagesServer Request URL: $url');
  print('getMessagesServer Request Method: GET');
  print('getMessagesServer Request Headers: {}');  // No headers in this case
  print('getMessagesServer Request Body: ');  // Empty body for this request

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'GET',
    body: '',
  );

  // Check if response is null
  if (response == null) {
    print('getMessagesServer: No response received.');
    return [];
  }

  // Log the response status code and body
  print('getMessagesServer Response Status Code: ${response.statusCode}');
  print('getMessagesServer Response Body: ${response.body}');

  // Handle the response
  if (response.statusCode == 200) {
    try {
      var messages = (jsonDecode(response.body) as List<dynamic>)
          .map((message) => ServerMessage.fromJson(message))
          .toList();
      print('getMessagesServer length: ${messages.length}');
      return messages;
    } catch (e) {
      print('getMessagesServer: Error decoding JSON - $e');
    }
  }

  return [];
}

Future<ServerMessage> sendMessageServer(String text, {String? pluginId}) async {
  // Construct the request URL
  final url = '${Env.apiBaseUrl}v1/messages?plugin_id=$pluginId';

  // Log the request details
  print('sendMessageServer Request URL: $url');
  print('sendMessageServer Request Method: POST');
  print('sendMessageServer Request Headers: {}');  // No headers in this case
  print('sendMessageServer Request Body: ${jsonEncode({'text': text})}');

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'POST',
    body: jsonEncode({'text': text}),
  );

  // Log the response status code and body
  print('sendMessageServer Response Status Code: ${response?.statusCode}');
  print('sendMessageServer Response Body: ${response?.body}');

  // Handle the response
  if (response == null) {
    throw Exception('Failed to receive response');
  }
  if (response.statusCode == 200) {
    try {
      return ServerMessage.fromJson(jsonDecode(response.body));
    } catch (e) {
      print('sendMessageServer: Error decoding JSON - $e');
      throw Exception('Failed to decode response');
    }
  } else {
    throw Exception('Failed to send message');
  }
}

Future<ServerMessage> getInitialPluginMessage(String? pluginId) async {
  // Construct the request URL
  final url = '${Env.apiBaseUrl}v1/initial-message?plugin_id=$pluginId';

  // Log the request details
  print('getInitialPluginMessage Request URL: $url');
  print('getInitialPluginMessage Request Method: POST');
  print('getInitialPluginMessage Request Headers: {}');  // No headers in this case
  print('getInitialPluginMessage Request Body: ');  // Empty body for this request

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'POST',
    body: '',
  );

  // Log the response status code and body
  print('getInitialPluginMessage Response Status Code: ${response?.statusCode}');
  print('getInitialPluginMessage Response Body: ${response?.body}');

  // Handle the response
  if (response == null) {
    throw Exception('Failed to receive response');
  }
  if (response.statusCode == 200) {
    try {
      return ServerMessage.fromJson(jsonDecode(response.body));
    } catch (e) {
      print('getInitialPluginMessage: Error decoding JSON - $e');
      throw Exception('Failed to decode response');
    }
  } else {
    throw Exception('Failed to get initial plugin message');
  }
}
