import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sockets/transcription_service.dart';

enum SttRequestBodyType {
  multipartForm,
  rawBinary,
  jsonBase64,
}

class SttFileUploadConfig {
  final String fileUploadUrl;
  final Map<String, String> fileUploadHeaders;
  final Map<String, dynamic> fileUploadBody;
  final String uploadUrlPath;
  final String fileUrlPath;
  final String uploadContentType;
  final String uploadMethod;

  const SttFileUploadConfig({
    required this.fileUploadUrl,
    required this.fileUploadHeaders,
    required this.fileUploadBody,
    this.uploadUrlPath = 'upload_url',
    this.fileUrlPath = 'file_url',
    this.uploadContentType = 'audio/wav',
    this.uploadMethod = 'PUT',
  });

  static SttFileUploadConfig falAI({required String apiKey}) {
    return SttFileUploadConfig(
      fileUploadUrl: 'https://rest.alpha.fal.ai/storage/upload/initiate',
      fileUploadHeaders: {
        'Authorization': 'Key $apiKey',
        'Content-Type': 'application/json',
      },
      fileUploadBody: {
        'content_type': 'audio/wav',
        'file_name': 'audio.wav',
      },
      uploadUrlPath: 'upload_url',
      fileUrlPath: 'file_url',
      uploadContentType: 'audio/wav',
      uploadMethod: 'PUT',
    );
  }

  factory SttFileUploadConfig.fromJson(Map<String, dynamic> json) {
    return SttFileUploadConfig(
      fileUploadUrl: json['file_upload_url'] as String,
      fileUploadHeaders: Map<String, String>.from(json['file_upload_headers'] ?? {}),
      fileUploadBody: Map<String, dynamic>.from(json['file_upload_body'] ?? {}),
      uploadUrlPath: json['upload_url_path'] as String? ?? 'upload_url',
      fileUrlPath: json['file_url_path'] as String? ?? 'file_url',
      uploadContentType: json['upload_content_type'] as String? ?? 'audio/wav',
      uploadMethod: json['upload_method'] as String? ?? 'PUT',
    );
  }

  Map<String, dynamic> toJson() => {
        'file_upload_url': fileUploadUrl,
        'file_upload_headers': fileUploadHeaders,
        'file_upload_body': fileUploadBody,
        'upload_url_path': uploadUrlPath,
        'file_url_path': fileUrlPath,
        'upload_content_type': uploadContentType,
        'upload_method': uploadMethod,
      };
}

class SchemaBasedSttProvider implements ISttProvider {
  final String apiUrl;
  final Map<String, String> defaultHeaders;
  final Map<String, String> defaultFields;
  final String audioFieldName;
  final SttResponseSchema schema;
  final SttRequestBodyType requestBodyType;
  final Map<String, dynamic> Function(String audioData)? jsonBodyBuilder;
  final SttFileUploadConfig? fileUploadConfig;
  final http.Client _client;

  SchemaBasedSttProvider({
    required this.apiUrl,
    required this.schema,
    this.defaultHeaders = const {},
    this.defaultFields = const {},
    this.audioFieldName = 'audio',
    this.requestBodyType = SttRequestBodyType.multipartForm,
    this.jsonBodyBuilder,
    this.fileUploadConfig,
  }) : _client = http.Client();

  factory SchemaBasedSttProvider.openAI({
    required String apiKey,
    String model = 'whisper-1',
    String language = 'en',
  }) {
    return SchemaBasedSttProvider(
      apiUrl: 'https://api.openai.com/v1/audio/transcriptions',
      schema: SttResponseSchema.openAI,
      defaultHeaders: {'Authorization': 'Bearer $apiKey'},
      defaultFields: {
        'model': model,
        'language': language,
        'response_format': 'verbose_json',
        'timestamp_granularities[]': 'segment',
      },
      audioFieldName: 'file',
    );
  }

  factory SchemaBasedSttProvider.deepgram({required String apiKey, String? language}) {
    final queryParams = <String, String>{
      'model': 'nova-3',
      'smart_format': 'true',
    };
    if (language != null) queryParams['language'] = language;

    final queryString = queryParams.entries.map((e) => '${e.key}=${e.value}').join('&');

    return SchemaBasedSttProvider(
      apiUrl: 'https://api.deepgram.com/v1/listen?$queryString',
      schema: SttResponseSchema.deepgram,
      defaultHeaders: {
        'Authorization': 'Token $apiKey',
        'Content-Type': 'audio/wav',
      },
      requestBodyType: SttRequestBodyType.rawBinary,
    );
  }

  factory SchemaBasedSttProvider.falAI({
    required String apiKey,
    String language = 'en',
    String task = 'transcribe',
    String chunkLevel = 'segment',
  }) {
    return SchemaBasedSttProvider(
      apiUrl: 'https://fal.run/fal-ai/wizper',
      schema: SttResponseSchema.falAI,
      defaultHeaders: {
        'Authorization': 'Key $apiKey',
        'Content-Type': 'application/json',
      },
      requestBodyType: SttRequestBodyType.jsonBase64,
      fileUploadConfig: SttFileUploadConfig.falAI(apiKey: apiKey),
      jsonBodyBuilder: (audioUrl) => {
        'audio_url': audioUrl,
        'task': task,
        'language': language,
        'chunk_level': chunkLevel,
      },
    );
  }

  factory SchemaBasedSttProvider.gemini({
    required String apiKey,
    String model = 'gemini-2.0-flash',
    String language = 'en',
  }) {
    return SchemaBasedSttProvider(
      apiUrl: 'https://generativelanguage.googleapis.com/v1beta/models/$model:generateContent?key=$apiKey',
      schema: SttResponseSchema.gemini,
      defaultHeaders: {
        'Content-Type': 'application/json',
      },
      requestBodyType: SttRequestBodyType.jsonBase64,
      jsonBodyBuilder: (base64Audio) => {
        'contents': [
          {
            'parts': [
              {
                'inline_data': {
                  'mime_type': 'audio/wav',
                  'data': base64Audio,
                }
              },
              {
                'text': 'Transcribe this audio to text in $language language. '
                    'Return only the transcription text, no explanations or formatting.',
              }
            ]
          }
        ],
        'generationConfig': {
          'temperature': 0.1,
          'maxOutputTokens': 8192,
        }
      },
    );
  }

  Future<String?> _uploadAudio(Uint8List audioData) async {
    if (fileUploadConfig == null) return null;

    try {
      // Step 1: Upload to get presigned URL
      final initResponse = await _client
          .post(
            Uri.parse(fileUploadConfig!.fileUploadUrl),
            headers: fileUploadConfig!.fileUploadHeaders,
            body: jsonEncode(fileUploadConfig!.fileUploadBody),
          )
          .timeout(const Duration(seconds: 30));

      if (initResponse.statusCode != 200) {
        debugPrint('[SchemaSTT] Upload init error: ${initResponse.statusCode} - ${initResponse.body}');
        return null;
      }

      final initData = jsonDecode(initResponse.body);
      final uploadUrl = JsonPathNavigator.getString(initData, fileUploadConfig!.uploadUrlPath);
      final fileUrl = JsonPathNavigator.getString(initData, fileUploadConfig!.fileUrlPath);

      if (uploadUrl == null || fileUrl == null) {
        debugPrint('[SchemaSTT] Failed to parse upload URLs');
        return null;
      }

      final uploadRequest = fileUploadConfig!.uploadMethod.toUpperCase() == 'PUT'
          ? _client.put(Uri.parse(uploadUrl),
              headers: {'Content-Type': fileUploadConfig!.uploadContentType}, body: audioData)
          : _client.post(Uri.parse(uploadUrl),
              headers: {'Content-Type': fileUploadConfig!.uploadContentType}, body: audioData);

      final uploadResponse = await uploadRequest.timeout(const Duration(seconds: 60));

      if (uploadResponse.statusCode != 200 && uploadResponse.statusCode != 201) {
        debugPrint('[SchemaSTT] Upload error: ${uploadResponse.statusCode}');
        return null;
      }

      return fileUrl;
    } catch (e) {
      debugPrint('[SchemaSTT] Upload exception: $e');
      return null;
    }
  }

  @override
  Future<SttTranscriptionResult?> transcribe(
    Uint8List audioData, {
    double audioOffsetSeconds = 0,
  }) async {
    try {
      final uri = Uri.parse(apiUrl);
      http.Response response;

      String? audioUrlFromUpload;
      if (fileUploadConfig != null) {
        audioUrlFromUpload = await _uploadAudio(audioData);
        if (audioUrlFromUpload == null) return null;
      }

      switch (requestBodyType) {
        case SttRequestBodyType.rawBinary:
          response =
              await _client.post(uri, headers: defaultHeaders, body: audioData).timeout(const Duration(seconds: 60));
          break;

        case SttRequestBodyType.jsonBase64:
          if (jsonBodyBuilder == null) {
            throw Exception('jsonBodyBuilder required for jsonBase64 request type');
          }
          final audioInput = audioUrlFromUpload ?? base64Encode(audioData);
          response = await _client
              .post(uri, headers: defaultHeaders, body: jsonEncode(jsonBodyBuilder!(audioInput)))
              .timeout(const Duration(seconds: 60));
          break;

        case SttRequestBodyType.multipartForm:
          final request = http.MultipartRequest('POST', uri)
            ..headers.addAll(defaultHeaders)
            ..fields.addAll(defaultFields)
            ..files.add(http.MultipartFile.fromBytes(audioFieldName, audioData, filename: 'audio.wav'));

          final streamedResponse = await request.send().timeout(const Duration(seconds: 60));
          response = await http.Response.fromStream(streamedResponse);
          break;
      }

      if (response.statusCode == 200) {
        return SttTranscriptionResult.fromJsonWithSchema(
          jsonDecode(response.body),
          schema,
          audioOffsetSeconds: audioOffsetSeconds,
        );
      }

      debugPrint('[SchemaSTT] Error: ${response.statusCode} - ${response.body}');
      return null;
    } catch (e) {
      debugPrint('[SchemaSTT] Exception: $e');
      rethrow;
    }
  }

  @override
  void dispose() {
    _client.close();
  }
}

class PollingTranscriptServiceFactory {
  static PurePollingSocket _createSocket(
    int sampleRate,
    BleAudioCodec codec,
    ISttProvider provider, {
    required String serviceId,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) {
    return PurePollingSocket(
      config: AudioPollingConfig(
        bufferDuration: bufferDuration,
        minBufferSizeBytes: sampleRate * 2,
        serviceId: serviceId,
        transcoder: transcoder ?? AudioTranscoderFactory.createToWav(sourceCodec: codec, sampleRate: sampleRate),
      ),
      sttProvider: provider,
    );
  }

  static TranscriptSegmentSocketService _createService(
    int sampleRate,
    BleAudioCodec codec,
    String language,
    PurePollingSocket socket, {
    bool includeSpeechProfile = false,
    String? source,
  }) {
    return TranscriptSegmentSocketService.withSocket(
      sampleRate,
      codec,
      language,
      socket,
      includeSpeechProfile: includeSpeechProfile,
      source: source,
    );
  }

  static PurePollingSocket createOpenAISocket(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    String model = 'whisper-1',
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createSocket(
        sampleRate,
        codec,
        SchemaBasedSttProvider.openAI(apiKey: apiKey, model: model, language: language),
        serviceId: 'openai-whisper',
        bufferDuration: bufferDuration,
        transcoder: transcoder,
      );

  static TranscriptSegmentSocketService createOpenAIService(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    String model = 'whisper-1',
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createService(
        sampleRate,
        codec,
        language,
        createOpenAISocket(sampleRate, codec, language,
            apiKey: apiKey, model: model, bufferDuration: bufferDuration, transcoder: transcoder),
        includeSpeechProfile: includeSpeechProfile,
        source: source,
      );

  static PurePollingSocket createDeepgramSocket(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createSocket(
        sampleRate,
        codec,
        SchemaBasedSttProvider.deepgram(apiKey: apiKey, language: language),
        serviceId: 'deepgram',
        bufferDuration: bufferDuration,
        transcoder: transcoder,
      );

  static TranscriptSegmentSocketService createDeepgramService(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createService(
        sampleRate,
        codec,
        language,
        createDeepgramSocket(sampleRate, codec, language,
            apiKey: apiKey, bufferDuration: bufferDuration, transcoder: transcoder),
        includeSpeechProfile: includeSpeechProfile,
        source: source,
      );

  static PurePollingSocket createFalAISocket(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createSocket(
        sampleRate,
        codec,
        SchemaBasedSttProvider.falAI(apiKey: apiKey, language: language),
        serviceId: 'fal-ai-whisper',
        bufferDuration: bufferDuration,
        transcoder: transcoder,
      );

  static TranscriptSegmentSocketService createFalAIService(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createService(
        sampleRate,
        codec,
        language,
        createFalAISocket(sampleRate, codec, language,
            apiKey: apiKey, bufferDuration: bufferDuration, transcoder: transcoder),
        includeSpeechProfile: includeSpeechProfile,
        source: source,
      );

  static PurePollingSocket createGeminiSocket(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    String model = 'gemini-2.0-flash',
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createSocket(
        sampleRate,
        codec,
        SchemaBasedSttProvider.gemini(apiKey: apiKey, model: model, language: language),
        serviceId: 'gemini',
        bufferDuration: bufferDuration,
        transcoder: transcoder,
      );

  static TranscriptSegmentSocketService createGeminiService(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    String model = 'gemini-2.0-flash',
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createService(
        sampleRate,
        codec,
        language,
        createGeminiSocket(sampleRate, codec, language,
            apiKey: apiKey, model: model, bufferDuration: bufferDuration, transcoder: transcoder),
        includeSpeechProfile: includeSpeechProfile,
        source: source,
      );

  static PurePollingSocket createSchemaBasedSocket(
    int sampleRate,
    BleAudioCodec codec, {
    required String apiUrl,
    required SttResponseSchema schema,
    Map<String, String> headers = const {},
    Map<String, String> fields = const {},
    String audioFieldName = 'audio',
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createSocket(
        sampleRate,
        codec,
        SchemaBasedSttProvider(
          apiUrl: apiUrl,
          schema: schema,
          defaultHeaders: headers,
          defaultFields: fields,
          audioFieldName: audioFieldName,
        ),
        serviceId: apiUrl,
        bufferDuration: bufferDuration,
        transcoder: transcoder,
      );

  static TranscriptSegmentSocketService createSchemaBasedService(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiUrl,
    required SttResponseSchema schema,
    Map<String, String> headers = const {},
    Map<String, String> fields = const {},
    String audioFieldName = 'audio',
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createService(
        sampleRate,
        codec,
        language,
        createSchemaBasedSocket(
          sampleRate,
          codec,
          apiUrl: apiUrl,
          schema: schema,
          headers: headers,
          fields: fields,
          audioFieldName: audioFieldName,
          bufferDuration: bufferDuration,
          transcoder: transcoder,
        ),
        includeSpeechProfile: includeSpeechProfile,
        source: source,
      );
}
