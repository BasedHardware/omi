// Automatic FlutterFlow imports
import '/backend/backend.dart';
import '/backend/schema/structs/index.dart';
import '/backend/schema/enums/enums.dart';
import '/backend/supabase/supabase.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart'; // Imports other custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'dart:convert';
import 'package:http/http.dart' as http; // Fixed the import
import "../../env/env.dart";

// Global variable defined here
String responseString = "";
dynamic chatHistory; // chatHistory but only action scope

var _client;

Future streamApiResponse(
  Future<dynamic> Function()? callbackAction,
) async {
  // Add your function code here!
  _client = http.Client();

  chatHistory = FFAppState().chatHistory;
  // FFAppState().update(() {
  //   FFAppState().chatHistory =
  //       saveChatHistory(chatHistory, convertToJSONRole(userPrompt, "user"));
  // });

  // Prepare Request

  final url = 'https://api.openai.com/v1/chat/completions';
  final headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ${Env.openAIApiKey}',
  };

  // Create Request
  String body = getApiBody(truncateChatHistory(chatHistory));
  var request = http.Request("POST", Uri.parse(url))
    ..headers.addAll(headers)
    ..body = body;

  debugPrint(
      'Body: $body \n\nHeader: $headers\n\nRequest fed: ${request.body}');

  responseString = "";
  // Before streaming response, add an empty ChatResponse object to chatHistory
  chatHistory = FFAppState().chatHistory;
  FFAppState().update(() {
    FFAppState().chatHistory = saveChatHistory(
        chatHistory, convertToJSONRole(responseString, "assistant"));
  });
  // FFAppState().addToChatHistory(ChatResponseStruct(
  //   author: 'assistant',
  //   content: '',
  // ));

  // Stream Response
  StringBuffer buffer = StringBuffer();

  final http.StreamedResponse response = await _client.send(request);

  response.stream.listen(
    (List<int> value) async {
      buffer.write(utf8.decode(value));
      String bufferString = buffer.toString();

      // Check for a complete message (or more than one)
      if (bufferString.contains("data:")) {
        // Split the buffer by 'data:' delimiter
        var jsonBlocks = bufferString
            .split('data:')
            .where((block) => block.isNotEmpty)
            .toList();

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
    // Try to parse the jsonString
    var decoded = json.decode(jsonString);
    // If the parsing is successful, the JSON is valid
    return true;
  } on FormatException {
    // If a FormatException is thrown, the JSON is not valid
    return false;
  } catch (e) {
    // If any other exception is thrown, the JSON is not valid
    return false;
  }
}

// // need this func to escape special chars
// void appendToResponseString(String content) {
//   // Escape and encode the content
//   String encodedContent = jsonEncode(content);

//   // Since jsonEncode adds extra quotes, remove them
//   encodedContent = encodedContent.substring(1, encodedContent.length - 1);

//   // Append the encoded content to responseString
//   responseString += encodedContent;
// }

void addToChatHistory(String data, callbackAction) {
  if (data.contains("content")) {
    ContentResponse contentResponse =
        ContentResponse.fromJson(jsonDecode(data));

    if (contentResponse.choices != null &&
        contentResponse.choices![0].delta != null &&
        contentResponse.choices![0].delta!.content != null) {
      String content = contentResponse.choices![0].delta!.content!;

      responseString += jsonEncodeString(content)!;

      chatHistory = updateChatHistoryAtIndex(
          convertToJSONRole(responseString, "assistant"),
          chatHistory.length - 1,
          chatHistory);
      FFAppState().update(() {
        FFAppState().chatHistory = chatHistory;
      });
      callbackAction();
    } else {
      // This handler is here in case  you want to send
      // non streaming requests, which return a different
      // structure response.
      if (contentResponse.choices![0].message != null) {
        String message = contentResponse.choices![0].message!.content!;
        // FFAppState().updateChatHistoryAtIndex(
        //   FFAppState().chatHistory.length - 1,
        //   (e) {
        //     return e..content = "$message";
        //   },
        // );
        callbackAction();
      }
    }
  }
}

void printChatHistory() {
  // Assuming 'myList' is your AppState variable and it's a list.
  var list = FFAppState().chatHistory;

  // Check if the list is not null.
  if (list != null) {
    // Print the entire list.
    debugPrint("List contents: $list");
  } else {
    // If the list is null, print a message indicating that.
    debugPrint("List is null");
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

class ContentResponse {
  String? id;
  String? object;
  int? created;
  String? model;
  List<Choices>? choices;

  ContentResponse(
      {this.id, this.object, this.created, this.model, this.choices});

  ContentResponse.fromJson(Map<String, dynamic> json) {
    // Fixed method name and parameters
    id = json['id']; // Fixed assignment syntax
    object = json['object']; // Fixed assignment syntax
    created = json['created'];
    model = json['model'];

    if (json['choices'] != null) {
      choices = <Choices>[];
      json['choices'].forEach((v) {
        choices!.add(new Choices.fromJson(v));
      });
    }
  }

  //sc2
  Map<String, dynamic> toJson() {
    final Map<String, dynamic> data = new Map<String, dynamic>();
    data['id'] = this.id;
    data['object'] = this.object;
    data['created'] = this.created;
    data['model'] = this.model;

    if (this.choices != null) {
      data['choices'] = this.choices!.map((v) => v.toJson()).toList();
    }

    return data;
  }
}

class Choices {
  int? index;
  Delta? delta;
  Message? message;
  String? finishReason;

  Choices(
      {this.index,
      this.delta,
      this.message,
      this.finishReason}); // Fixed spacing

  Choices.fromJson(Map<String, dynamic> json) {
    String? a = json['message'].toString();
    index = json['index'];
    delta = json['delta'] != null ? new Delta.fromJson(json['delta']) : null;
    message = json['message'] != null
        ? Message.fromJson(json['message'])
        : null; // Corrected
    finishReason = json['finish_reason']; // Fixed assignment syntax
  }

  //sc1
  Map<String, dynamic> toJson() {
    final Map<String, dynamic> data = new Map<String, dynamic>();
    data['index'] = this.index;

    if (this.delta != null) {
      data['delta'] = this.delta!.toJson();
    }
    data['finish_reason'] = this.finishReason;
    return data;
  }
}

class Delta {
  String? content;

  Delta({this.content});

  Delta.fromJson(Map<String, dynamic> json) {
    content = json['content'];
  }

  Map<String, dynamic> toJson() {
    final Map<String, dynamic> data = new Map<String, dynamic>();
    data['content'] = this.content;
    return data;
  }
}

class Message {
  String? role;
  String? content;

  Message({this.role, this.content});

  Message.fromJson(Map<String, dynamic> json) {
    role = json['role'];
    content = json['content'];
  }

  Map<String, dynamic> toJson() {
    final Map<String, dynamic> data = new Map<String, dynamic>();
    data['role'] = this.role;
    data['content'] = this.content;
    return data;
  }
  // Add your function code here!
}
