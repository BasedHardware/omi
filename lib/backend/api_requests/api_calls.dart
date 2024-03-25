import 'dart:convert';

import '/flutter_flow/flutter_flow_util.dart';
import 'api_manager.dart';
import '../../env/env.dart';

export 'api_manager.dart' show ApiCallResponse;

const _kPrivateApiFunctionName = 'ffPrivateApiCall';

class StructuredMemoryCall {
  static Future<ApiCallResponse> call({
    String? memory = '',
  }) async {
    final ffApiRequestBody = '''
{
  "model": "gpt-4-1106-preview",
  "messages": [
    {
      "role": "user",
      "content": "Generate a suitable title for the summary based on the content below and write it in the beginning. Also, Identify the specific details in the conversation and summarize specific facts that are important to remember or action-items in very concise short points in second person. Respond in bullet points. If no valid memories/topics could be extracted OR if conversation is empty, reply with \\"N/A\\". Here is the conversation: \\"\\"\\"$memory\\"\\"\\""
    }
  ]
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'StructuredMemory',
      apiUrl: 'https://api.openai.com/v1/chat/completions',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': 'Bearer ${Env.openAIApiKey}',
      },
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: true,
      cache: false,
      alwaysAllowBody: false,
    );
  }

  static String? responsegpt(dynamic response) =>
      castToType<String>(getJsonField(
        response,
        r'''$.choices[0].message.content''',
      ));
}

class ChatGPTFeedbackCall {
  static Future<ApiCallResponse> call({
    String? memory = '',
    String? structuredMemory = '',
  }) async {
    final ffApiRequestBody = '''
{
  "model": "gpt-4-1106-preview",
  "messages": [
    {
      "role": "user",
      "content": "you are Comind, the harsh honest and direct AI mentor who observes the conversation the user is having. Based on the below conversation that your mdentee had with someone, respond with a message to your mentee in short sentences. Make it very specific, short, concise, straightforward and include examples. In your response, keep everything on the same line without \\n symbols, do not include quotes symbols. Ask clarifying questions. Conversation was taken with bad-quality microphone, so do not include anything about clarity, conciseness or simillar. Raw conversation: \\n\\"\\"\\"$memory\\"\\"\\" "
    }
  ]
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'chatGPT Feedback',
      apiUrl: 'https://api.openai.com/v1/chat/completions',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': 'Bearer ${Env.openAIApiKey}',
      },
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: true,
      decodeUtf8: true,
      cache: false,
      alwaysAllowBody: false,
    );
  }

  static String? responsegpt(dynamic response) =>
      castToType<String>(getJsonField(
        response,
        r'''$.choices[:].message.content''',
      ));
}

class TestCall {
  static Future<ApiCallResponse> call({
    String? memory = '',
    String? structuredMemory = '',
  }) async {
    const ffApiRequestBody = '''
{
    "model": "gpt-3.5-turbo-0125",
    "response_format": { "type": "json_object" },
    "messages": [
      {
        "role": "system",
        "content": "You are a helpful assistant designed to output JSON in this format: key = memory. value = {your response}"
      },
      {
        "role": "user",
        "content": "return 5 random memories"
      }
    ]
  }''';
    return ApiManager.instance.makeApiCall(
      callName: 'test',
      apiUrl: 'https://api.openai.com/v1/chat/completions',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': 'Bearer ${Env.openAIApiKey}',
      },
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: true,
      decodeUtf8: true,
      cache: false,
      alwaysAllowBody: false,
    );
  }

  static List<String>? responsegpt(dynamic response) => (getJsonField(
        response,
        r'''$.choices[:].message.content''',
        true,
      ) as List?)
          ?.withoutNulls
          .map((x) => castToType<String>(x))
          .withoutNulls
          .toList();
}

class ChatGPTWhisperCall {
  static Future<ApiCallResponse> call({
    FFUploadedFile? file,
  }) async {
    return ApiManager.instance.makeApiCall(
      callName: 'chatGPT Whisper',
      apiUrl: 'https://api.openai.com/v1/audio/transcriptions',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'multipart/form-data',
        'Authorization': 'Bearer ${Env.openAIApiKey}',
      },
      params: {
        'file': file,
        'model': "whisper-1",
      },
      bodyType: BodyType.MULTIPART,
      returnBody: true,
      encodeBodyUtf8: true,
      decodeUtf8: true,
      cache: false,
      alwaysAllowBody: false,
    );
  }

  static String? responsegpt(dynamic response) =>
      castToType<String>(getJsonField(
        response,
        r'''$.choices[:].message.content''',
      ));
}

class VoiceCommandRespondCall {
  static Future<ApiCallResponse> call({
    String? memory = '',
    String? longTermMemory = '',
  }) async {
    final ffApiRequestBody = '''
{
  "model": "gpt-4-1106-preview",
  "messages": [
    {
      "role": "system",
      "content": "LONG TERM MEMORIES: \\"\\"\\"$longTermMemory\\"\\"\\"\\n\\n CONVERSATION: \\"\\"\\"$memory\\"\\"\\"\\n\\n Your name is Sama and you are harsh, funny, honest mentor who observes the conversation the user is having, and they have asked you a question. You respond as concisely as possible. Figure out the question asked in the latest sentence and return just your answer as best you can, concisely. \\n\\nYour answer:"
    }
  ]
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'voiceCommandRespond',
      apiUrl: 'https://api.openai.com/v1/chat/completions',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': 'Bearer ${Env.openAIApiKey}',
      },
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: true,
      cache: false,
      alwaysAllowBody: false,
    );
  }

  static String? responsegpt(dynamic response) =>
      castToType<String>(getJsonField(
        response,
        r'''$.choices[:].message.content''',
      ));
}

class DailyMemoriesCall {
  static Future<ApiCallResponse> call({
    String? memories = '',
  }) async {
    final ffApiRequestBody = '''
{
  "model": "gpt-4-1106-preview",
  "messages": [
    {
      "role": "user",
      "content": "you are the harsh honest mentor who observes the conversations the user had during the day. Based on the above conversations that your mentee had with someone, what specific message would you text the mentee? don't explain, just write the final output. make it interesting with an insight, specific, professional and simple to read: $memories."
    }
  ]
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'DailyMemories',
      apiUrl: 'https://api.openai.com/v1/chat/completions',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ${Env.openAIApiKey}',
      },
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: true,
      cache: false,
      alwaysAllowBody: false,
    );
  }

  static String? responsegpt(dynamic response) =>
      castToType<String>(getJsonField(
        response,
        r'''$.choices[:].message.content''',
      ));
}

class SummariesCall {
  static Future<ApiCallResponse> call({
    String? structuredMemories = '',
  }) async {
    final ffApiRequestBody = '''
{
  "model": "gpt-4-1106-preview",
  "messages": [
    {
      "role": "user",
      "content": "Based on my recent memories below, summarize everything into 3-4 most important facts I need to remember. write the final output only and make it very short and concise, less than 200 symbols total as bulletpoints. Make it interesting with an insight, specific, professional and simple to read: $structuredMemories."
    }
  ]
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'Summaries',
      apiUrl: 'https://api.openai.com/v1/chat/completions',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ${Env.openAIApiKey}',
      },
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: true,
      cache: false,
      alwaysAllowBody: false,
    );
  }

  static String? responsegpt(dynamic response) =>
      castToType<String>(getJsonField(
        response,
        r'''$.choices[:].message.content''',
      ));
}

class IsFeeedbackUsefulCall {
  static Future<ApiCallResponse> call({
    String? feedback = '',
    String? memory = '',
  }) async {
    final ffApiRequestBody = '''
{
  "model": "gpt-3.5-turbo",
  "messages": [
    {
      "role": "user",
      "content": "You are a mentor of a busy entrepreneur. Below is a conversation that your mentee had \\"$memory\\". You provided the following feedback: \\"$feedback\\". Determine if the feedback is actually insightful and important to the mentee's life or not. Return only Show or Hide. If important, return Show. If not, return Hide."
    }
  ]
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'IsFeeedbackUseful',
      apiUrl: 'https://api.openai.com/v1/chat/completions',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': 'Bearer ${Env.openAIApiKey}',
      },
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: true,
      decodeUtf8: true,
      cache: false,
      alwaysAllowBody: false,
    );
  }

  static String? responsegpt(dynamic response) =>
      castToType<String>(getJsonField(
        response,
        r'''$.choices[:].message.content''',
      ));
}

class BoolTestCall {
  static Future<ApiCallResponse> call({
    String? feedback = '',
    String? memory = '',
  }) async {
    const ffApiRequestBody = '''
{
  "model": "gpt-3.5-turbo",
  "messages": [
    {
      "role": "user",
      "content": "Return in boolean format: True"
    }
  ]
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'BoolTest',
      apiUrl: 'https://api.openai.com/v1/chat/completions',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ${Env.openAIApiKey}',
      },
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: true,
      cache: false,
      alwaysAllowBody: false,
    );
  }

  static String? responsegpt(dynamic response) =>
      castToType<String>(getJsonField(
        response,
        r'''$.choices[:].message.content''',
      ));
}

class SendFullPromptCall {
  static Future<ApiCallResponse> call({
    dynamic promptJson,
  }) async {
    final prompt = _serializeJson(promptJson);
    final ffApiRequestBody = '''
{
  "model": "gpt-4-1106-preview",
  "messages": $prompt
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'sendFullPrompt',
      apiUrl: 'https://api.openai.com/v1/chat/completions',
      callType: ApiCallType.POST,
      headers: {
        'Authorization': 'Bearer ${Env.openAIApiKey}',
      },
      params: {},
      body: ffApiRequestBody,
      bodyType: BodyType.JSON,
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: true,
      cache: false,
      alwaysAllowBody: false,
    );
  }

  static dynamic createdTimestamp(dynamic response) => getJsonField(
        response,
        r'''$.created''',
      );
  static dynamic role(dynamic response) => getJsonField(
        response,
        r'''$.choices[:].message.role''',
      );
  static dynamic content(dynamic response) => getJsonField(
        response,
        r'''$.choices[:].message.content''',
      );
}

class ApifyCall {
  static Future<ApiCallResponse> call({
    String? apiToken = 'apify_api_vdN6qsOzIf92BlLECuuYakMiwwYiwy14uPOG',
  }) async {
    const ffApiRequestBody = '''
{
 "handles": [
    "Apify"
  ],
  "tweetsDesired": 10,
  "addUserInfo": true,
  "startUrls": [],
  "proxyConfig": {
    "useApifyProxy": true
  }
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'apify',
      apiUrl:
          'https://api.apify.com/v2/acts/u6ppkMWAx2E2MpEuF/runs?token=$apiToken',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'application/json',
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

class GetPostsCall {
  static Future<ApiCallResponse> call({
    String? apiToken = 'apify_api_vdN6qsOzIf92BlLECuuYakMiwwYiwy14uPOG',
  }) async {
    return ApiManager.instance.makeApiCall(
      callName: 'getPosts',
      apiUrl:
          'https://api.apify.com/v2/acts/quacker~twitter-scraper/runs/last?token=apify_api_vdN6qsOzIf92BlLECuuYakMiwwYiwy14uPOG',
      callType: ApiCallType.GET,
      headers: {
        'Content-Type': 'application/json',
      },
      params: {},
      returnBody: true,
      encodeBodyUtf8: false,
      decodeUtf8: false,
      cache: false,
      alwaysAllowBody: false,
    );
  }
}

class VectorizeCall {
  static Future<ApiCallResponse> call({
    String? input = '',
  }) async {
    final ffApiRequestBody = '''
{
  "input": "$input",
  "model": "text-embedding-3-small"
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'Vectorize',
      apiUrl: 'https://api.openai.com/v1/embeddings',
      callType: ApiCallType.POST,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ${Env.openAIApiKey}',
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

  static List<double>? embedding(dynamic response) => (getJsonField(
        response,
        r'''$.data[0].embedding''',
        true,
      ) as List?)
          ?.withoutNulls
          .map((x) => castToType<double>(x))
          .withoutNulls
          .toList();
}

class CreateVectorPineconeCall {
  static Future<ApiCallResponse> call({
    List<double>? vectorList,
    String? structuredMemory = '',
    String? id = '',
  }) async {
    final vector = _serializeList(vectorList);

    final ffApiRequestBody = '''
{
  "vectors": [
    {
      "id": "$id",
      "values": $vector,
      "metadata": {
        "structuredMemory": "$structuredMemory"
      }
    }
  ],
  "namespace": "ns1"
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'createVectorPinecone',
      apiUrl:
          'https://index-i7j24t4.svc.gcp-starter.pinecone.io/vectors/upsert',
      callType: ApiCallType.POST,
      headers: {
        'Api-Key': Env.pineconeApiKey,
        'Content-Type': 'application/json',
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

class QueryVectorsCall {
  static Future<ApiCallResponse> call({
    List<double>? vectorList,
  }) async {
    final vector = _serializeList(vectorList);

    final ffApiRequestBody = '''
{
  "namespace": "ns1",
  "vector": $vector,
  "topK": 10,
  "includeValues": true,
  "includeMetadata": true,
  "filter": {
    "genre": {
    }
  }
}''';
    return ApiManager.instance.makeApiCall(
      callName: 'QueryVectors',
      apiUrl: 'https://index-i7j24t4.svc.gcp-starter.pinecone.io/query',
      callType: ApiCallType.POST,
      headers: {
        'Api-Key': Env.pineconeApiKey,
        'Content-Type': 'application/json',
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

  static List? metadata(dynamic response) => getJsonField(
        response,
        r'''$.matches[:].metadata''',
        true,
      ) as List?;
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
