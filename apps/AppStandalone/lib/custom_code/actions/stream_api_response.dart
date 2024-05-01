// Automatic FlutterFlow imports
import '/backend/backend.dart';
import '/backend/schema/structs/index.dart';
import '/backend/schema/enums/enums.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart'; // Imports other custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
import './streaming_models.dart';

// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'dart:convert';
import 'package:http/http.dart' as http; // Fixed the import
import "../../env/env.dart";

// Global variable defined here
String responseString = "";
dynamic chatHistory; // chatHistory but only action scope

var _client;

Future streamApiResponse(Future<dynamic> Function()? callbackAction,) async {
  // Add your function code here!
  _client = http.Client();

  chatHistory = FFAppState().chatHistory;

  final url = 'https://api.openai.com/v1/chat/completions';
  final headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ${Env.openAIApiKey}',
    'OpenAI-Organization': Env.openAIOrganization,
  };

  // Create Request
  String body = getApiBody(truncateChatHistory(chatHistory));
  var request = http.Request("POST", Uri.parse(url))
    ..headers.addAll(headers)
    ..body = body;

  debugPrint('Body: $body \n\nHeader: $headers\n\nRequest fed: ${request.body}');

  responseString = "";
  // Before streaming response, add an empty ChatResponse object to chatHistory
  chatHistory = FFAppState().chatHistory;
  FFAppState().update(() {
    FFAppState().chatHistory = saveChatHistory(chatHistory, convertToJSONRole(responseString, "assistant"));
  });

  StringBuffer buffer = StringBuffer();

  final http.StreamedResponse response = await _client.send(request);

  response.stream.listen(
        (List<int> value) async {
      buffer.write(utf8.decode(value));
      String bufferString = buffer.toString();

      // Check for a complete message (or more than one)
      if (bufferString.contains("data:")) {
        // Split the buffer by 'data:' delimiter
        var jsonBlocks = bufferString.split('data:').where((block) => block.isNotEmpty).toList();

        int processedBlocks = 0;
        for (var jsonBlock in jsonBlocks) {
          if (isValidJson(jsonBlock)) {
            addToChatHistory(jsonBlock, callbackAction);
            processedBlocks++;
          } else {
            bufferString = 'data: ' + jsonBlock;
          }
        }
        buffer.clear();
        if (processedBlocks < jsonBlocks.length) {
          //we have a partial message
          buffer.write(bufferString);
          print('Partial message in queue: $bufferString');
        }
      }
    }, // Need to add handling for non-streaming responses

    onError: (error) {
      // Handle any errors that occur during streaming
      debugPrint('Stream error: $error');
    },
    onDone: () {
      // Handle when streaming is finished
      debugPrint('Stream completed');
    },
  );
}

bool isValidJson(String jsonString) {
  try {
    var decoded = json.decode(jsonString);
    return true;
  } catch (e) {
    return false;
  }
}

void addToChatHistory(String data, callbackAction) {
  if (data.contains("content")) {
    ContentResponse contentResponse = ContentResponse.fromJson(jsonDecode(data));

    if (contentResponse.choices != null &&
        contentResponse.choices![0].delta != null &&
        contentResponse.choices![0].delta!.content != null) {
      String content = contentResponse.choices![0].delta!.content!;

      responseString += jsonEncodeString(content)!;

      chatHistory =
          updateChatHistoryAtIndex(convertToJSONRole(responseString, "assistant"), chatHistory.length - 1, chatHistory);
      FFAppState().update(() {
        FFAppState().chatHistory = chatHistory;
      });
      callbackAction();
    }
  }
}

String getApiBody(dynamic chatHistory) {
  // Added return type 'String'
  String body;
  body = jsonEncode({
    "model": "gpt-4-1106-preview",
    "messages": chatHistory,
    "stream": true,
  });
  return body;
}
