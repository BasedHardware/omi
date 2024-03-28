import 'dart:convert';
import 'dart:typed_data';
import '../schema/structs/index.dart';

import '/flutter_flow/flutter_flow_util.dart';
import 'api_manager.dart';

export 'api_manager.dart' show ApiCallResponse;

const _kPrivateApiFunctionName = 'ffPrivateApiCall';

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
            'Bearer <add_key>',
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

class ApiPagingParams {
  int nextPageNumber = 0;
  int numItems = 0;
  dynamic lastResponse;

  ApiPagingParams({
    required this.nextPageNumber,
    required this.numItems,
    required this.lastResponse,
  });

  @override
  String toString() =>
      'PagingParams(nextPageNumber: $nextPageNumber, numItems: $numItems, lastResponse: $lastResponse,)';
}

String _serializeList(List? list) {
  list ??= <String>[];
  try {
    return json.encode(list);
  } catch (_) {
    return '[]';
  }
}

String _serializeJson(dynamic jsonVar, [bool isList = false]) {
  jsonVar ??= (isList ? [] : {});
  try {
    return json.encode(jsonVar);
  } catch (_) {
    return isList ? '[]' : '{}';
  }
}
