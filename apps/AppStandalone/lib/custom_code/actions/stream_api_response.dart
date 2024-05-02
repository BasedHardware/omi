// Automatic FlutterFlow imports
import '/backend/backend.dart';
import '/backend/schema/structs/index.dart';
import '/backend/schema/enums/enums.dart';
import 'package:sama/backend/api_requests/api_calls.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart';
import '/flutter_flow/custom_functions.dart';
import 'package:flutter/material.dart';
import './streaming_models.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import "../../env/env.dart";

initAssistantResponse() {
  FFAppState().update(() {
    FFAppState().chatHistory = saveChatHistory(FFAppState().chatHistory, convertToJSONRole("", "assistant"));
  });
}

Future streamApiResponse(
  String context,
  Future<dynamic> Function(String) callback,
) async {
  var _client = http.Client();
  final url = 'https://api.openai.com/v1/chat/completions';
  final headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ${Env.openAIApiKey}',
    'OpenAI-Organization': Env.openAIOrganization,
  };

  // String body = qaStreamedBody(context, retrieveMostRecentMessages(FFAppState().chatHistory), () => {});
  String body =
      qaStreamedFullMemories(FFAppState().memories, retrieveMostRecentMessages(FFAppState().chatHistory), () => {});
  var request = http.Request("POST", Uri.parse(url))
    ..headers.addAll(headers)
    ..body = body;

  initAssistantResponse();
  final http.StreamedResponse response = await _client.send(request);
  _listStream(response, callback);
}

_listStream(response, callback) {
  StringBuffer buffer = StringBuffer();
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
            handlePartialResponseContent(jsonBlock, callback);
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
    },
    onError: (error) => debugPrint('Stream error: $error'),
    onDone: () => debugPrint('Stream completed'),
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

void handlePartialResponseContent(String data, Future<dynamic> Function(String) callback) {
  if (data.contains("content")) {
    ContentResponse contentResponse = ContentResponse.fromJson(jsonDecode(data));
    if (contentResponse.choices != null &&
        contentResponse.choices![0].delta != null &&
        contentResponse.choices![0].delta!.content != null) {
      String content = jsonEncodeString(contentResponse.choices![0].delta!.content!)!;
      callback(content);
    }
  }
}
// TODO: remove ``Great job activating me! I'll passively listen to your voice and will``
