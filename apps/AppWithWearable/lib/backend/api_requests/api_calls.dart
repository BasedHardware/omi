import 'dart:convert';

import '/flutter_flow/flutter_flow_util.dart';
import 'api_manager.dart';

export 'api_manager.dart' show ApiCallResponse;


/// Start deepgram Group Code

class DeepgramGroup {
  static String baseUrl = 'https://api.deepgram.com/v1';
  static Map<String, String> headers = {};
  static ListenCall listenCall = ListenCall();
}

class ListenCall {
  Future<ApiCallResponse> call({
    String? url = '',
  }) async {
    final ffApiRequestBody = '''
{"url":"${url}"}''';
    return ApiManager.instance.makeApiCall(
      callName: 'listen',
      apiUrl: '${DeepgramGroup.baseUrl}/listen?model=nova-2&smart_format=true',
      callType: ApiCallType.POST,
      headers: {},
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: false,
      cache: false,
      alwaysAllowBody: false,
    );
  }
}

/// End deepgram Group Code

/// Start Mistral AI API Group Code

class MistralAIAPIGroup {
  static String baseUrl = 'https://api.mistral.ai/v1';
  static Map<String, String> headers = {};
  static CreateChatCompletionCall createChatCompletionCall =
      CreateChatCompletionCall();
  static CreateEmbeddingCall createEmbeddingCall = CreateEmbeddingCall();
  static ListModelsCall listModelsCall = ListModelsCall();
}

class CreateChatCompletionCall {
  Future<ApiCallResponse> call() async {
    final ffApiRequestBody = '''
""''';
    return ApiManager.instance.makeApiCall(
      callName: 'createChatCompletion',
      apiUrl: '${MistralAIAPIGroup.baseUrl}/chat/completions',
      callType: ApiCallType.POST,
      headers: {},
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: false,
      cache: false,
      alwaysAllowBody: false,
    );
  }
}

class CreateEmbeddingCall {
  Future<ApiCallResponse> call() async {
    final ffApiRequestBody = '''
{
  "model": "mistral-embed",
  "input": [
    ""
  ],
  "encoding_format": "float"
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'createEmbedding',
      apiUrl: '${MistralAIAPIGroup.baseUrl}/embeddings',
      callType: ApiCallType.POST,
      headers: {},
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: false,
      cache: false,
      alwaysAllowBody: false,
    );
  }
}

class ListModelsCall {
  Future<ApiCallResponse> call() async {
    return ApiManager.instance.makeApiCall(
      callName: 'listModels',
      apiUrl: '${MistralAIAPIGroup.baseUrl}/models',
      callType: ApiCallType.GET,
      headers: {},
      params: {},
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: false,
      cache: false,
      alwaysAllowBody: false,
    );
  }
}

/// End Mistral AI API Group Code

/// Start OpenAI  Group Code

class OpenAIGroup {
  static String baseUrl = 'https://api.openai.com/v1';
  static Map<String, String> headers = {
    'Content-Type': 'application/json',
  };
  static SendFullPromptCall sendFullPromptCall = SendFullPromptCall();
}

class SendFullPromptCall {
  Future<ApiCallResponse> call({
    String? apiKey = '',
    dynamic promptJson,
  }) async {
    final prompt = _serializeJson(promptJson);
    final ffApiRequestBody = '''
{
  "model": "gpt-3.5-turbo",
  "messages": ${prompt}
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'Send Full Prompt',
      apiUrl: '${OpenAIGroup.baseUrl}/chat/completions',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ${apiKey}',
      },
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: false,
      cache: false,
      alwaysAllowBody: false,
    );
  }
}

/// End OpenAI  Group Code

class WhisperDCall {
  static Future<ApiCallResponse> call({
    FFUploadedFile? file,
    String? key = '',
  }) async {
    return ApiManager.instance.makeApiCall(
      callName: 'WHISPER D',
      apiUrl: 'https://api.openai.com/v1/audio/transcriptions',
      callType: ApiCallType.POST,
      headers: {
        'Authorization':
            'Bearer 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',
        'Content-Type': 'multipart/form-data',
      },
      params: {
        'file': file,
        'model': "whisper-1",
      },
      bodyType: BodyType.MULTIPART,
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: false,
      cache: false,
      alwaysAllowBody: false,
    );
  }

  static dynamic text(dynamic response) => getJsonField(
        response,
        r'''$.text''',
      );
}


String _serializeJson(dynamic jsonVar, [bool isList = false]) {
  jsonVar ??= (isList ? [] : {});
  try {
    return json.encode(jsonVar);
  } catch (_) {
    return isList ? '[]' : '{}';
  }
}
