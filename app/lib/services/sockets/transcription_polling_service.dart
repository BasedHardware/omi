import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:omi/services/sockets/pure_polling.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/models/stt_result.dart';

enum SttRequestBodyType {
  multipartForm,
  rawBinary,
  jsonBase64;

  /// Convert from string request type (from SttRequestType constants)
  static SttRequestBodyType fromString(String? type) {
    switch (type) {
      case 'raw_binary':
        return SttRequestBodyType.rawBinary;
      case 'json_base64':
        return SttRequestBodyType.jsonBase64;
      case 'multipart_form':
      default:
        return SttRequestBodyType.multipartForm;
    }
  }
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
    SttRequestBodyType? requestBodyType,
    String? requestType, // String version for unified config
    this.jsonBodyBuilder,
    this.fileUploadConfig,
  })  : requestBodyType = requestBodyType ?? SttRequestBodyType.fromString(requestType),
        _client = http.Client();

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
    String model = 'gemini-2.5-flash',
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

  // ref: https://github.com/ggml-org/whisper.cpp
  factory SchemaBasedSttProvider.localWhisper({
    String host = '127.0.0.1',
    int port = 8080,
    String responseFormat = 'verbose_json',
    double temperature = 0.0,
    double temperatureInc = 0.2,
  }) {
    return SchemaBasedSttProvider(
      apiUrl: 'http://$host:$port/inference',
      schema: SttResponseSchema.openAI, // whisper.cpp uses same format as OpenAI
      defaultHeaders: {},
      defaultFields: {
        'temperature': temperature.toString(),
        'temperature_inc': temperatureInc.toString(),
        'response_format': responseFormat,
      },
      audioFieldName: 'file',
      requestBodyType: SttRequestBodyType.multipartForm,
    );
  }

  /// OpenAI GPT-4o Transcribe with speaker diarization
  /// ref: https://platform.openai.com/docs/models/gpt-4o-transcribe-diarize
  factory SchemaBasedSttProvider.openAIDiarize({
    required String apiKey,
    String language = 'en',
  }) {
    return SchemaBasedSttProvider(
      apiUrl: 'https://api.openai.com/v1/audio/transcriptions',
      schema: SttResponseSchema.openAIDiarize,
      defaultHeaders: {'Authorization': 'Bearer $apiKey'},
      defaultFields: {
        'model': 'gpt-4o-transcribe-diarize',
        'language': language,
        'response_format': 'diarized_json',
        'chunking_strategy': 'auto',
      },
      audioFieldName: 'file',
    );
  }

  Future<String?> _uploadAudio(Uint8List audioBytes) async {
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
              headers: {'Content-Type': fileUploadConfig!.uploadContentType}, body: audioBytes)
          : _client.post(Uri.parse(uploadUrl),
              headers: {'Content-Type': fileUploadConfig!.uploadContentType}, body: audioBytes);

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
    dynamic audioData, {
    double audioOffsetSeconds = 0,
  }) async {
    final Uint8List audioBytes = audioData is Uint8List ? audioData : Uint8List.fromList(audioData);
    try {
      final uri = Uri.parse(apiUrl);
      http.Response response;

      String? audioUrlFromUpload;
      if (fileUploadConfig != null) {
        audioUrlFromUpload = await _uploadAudio(audioBytes);
        if (audioUrlFromUpload == null) return null;
      }

      switch (requestBodyType) {
        case SttRequestBodyType.rawBinary:
          response =
              await _client.post(uri, headers: defaultHeaders, body: audioBytes).timeout(const Duration(seconds: 60));
          break;

        case SttRequestBodyType.jsonBase64:
          if (jsonBodyBuilder == null) {
            throw Exception('jsonBodyBuilder required for jsonBase64 request type');
          }
          final audioInput = audioUrlFromUpload ?? base64Encode(audioBytes);
          response = await _client
              .post(uri, headers: defaultHeaders, body: jsonEncode(jsonBodyBuilder!(audioInput)))
              .timeout(const Duration(seconds: 60));
          break;

        case SttRequestBodyType.multipartForm:
          final request = http.MultipartRequest('POST', uri)
            ..headers.addAll(defaultHeaders)
            ..fields.addAll(defaultFields)
            ..files.add(http.MultipartFile.fromBytes(audioFieldName, audioBytes, filename: 'audio.wav'));

          final streamedResponse = await request.send().timeout(const Duration(seconds: 60));
          response = await http.Response.fromStream(streamedResponse);
          break;
      }

      if (response.statusCode == 200) {
        CustomSttLogService.instance.info('SchemaSTT', 'Transcription successful');
        return SttTranscriptionResult.fromJsonWithSchema(
          jsonDecode(response.body),
          schema,
          audioOffsetSeconds: audioOffsetSeconds,
        );
      }

      final errorMsg = 'HTTP ${response.statusCode} - ${response.body}';
      CustomSttLogService.instance.error('SchemaSTT', errorMsg);
      return null;
    } catch (e) {
      CustomSttLogService.instance.error('SchemaSTT', 'Exception: $e');
      rethrow;
    }
  }

  @override
  void dispose() {
    _client.close();
  }
}
