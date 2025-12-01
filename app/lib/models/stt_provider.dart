import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/models/stt_response_schema.dart';

enum SttProvider {
  omi,
  openai,
  deepgram,
  deepgramLive,
  falai,
  gemini,
  geminiLive,
  localWhisper,
  custom,
  customLive;

  static SttProvider fromString(String value) {
    return SttProvider.values.firstWhere(
      (e) => e.name == value,
      orElse: () => SttProvider.omi,
    );
  }
}

class SttProviderConfig {
  final SttProvider provider;
  final String displayName;
  final String description;
  final IconData icon;
  final bool requiresApiKey;
  final Map<String, dynamic> requestConfig;
  final SttResponseSchema responseSchema;

  const SttProviderConfig({
    required this.provider,
    required this.displayName,
    required this.description,
    required this.icon,
    this.requiresApiKey = false,
    required this.requestConfig,
    required this.responseSchema,
  });

  static const _configs = <SttProvider, SttProviderConfig>{
    SttProvider.omi: SttProviderConfig(
      provider: SttProvider.omi,
      displayName: 'Omi',
      description: 'Omi\'s optimized transcription service',
      icon: FontAwesomeIcons.robot,
      requestConfig: {},
      responseSchema: SttResponseSchema(),
    ),
    SttProvider.openai: SttProviderConfig(
      provider: SttProvider.openai,
      displayName: 'OpenAI Whisper',
      description: 'OpenAI Whisper API - High accuracy',
      icon: FontAwesomeIcons.brain,
      requiresApiKey: true,
      requestConfig: {
        'api_url': 'https://api.openai.com/v1/audio/transcriptions',
        'request_type': 'multipart_form',
        'headers': {'Authorization': 'Bearer YOUR_API_KEY'},
        'fields': {
          'model': 'whisper-1',
          'language': 'en',
          'response_format': 'verbose_json',
          'timestamp_granularities[]': 'segment',
        },
        'audio_field_name': 'file',
      },
      responseSchema: SttResponseSchema.openAI,
    ),
    SttProvider.deepgram: SttProviderConfig(
      provider: SttProvider.deepgram,
      displayName: 'Deepgram',
      description: 'Deepgram Nova - Fast & accurate (polling)',
      icon: FontAwesomeIcons.waveSquare,
      requiresApiKey: true,
      requestConfig: {
        'api_url': 'https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true',
        'request_type': 'raw_binary',
        'headers': {
          'Authorization': 'Token YOUR_API_KEY',
          'Content-Type': 'audio/wav',
        },
      },
      responseSchema: SttResponseSchema.deepgram,
    ),
    SttProvider.deepgramLive: SttProviderConfig(
      provider: SttProvider.deepgramLive,
      displayName: 'Deepgram Live',
      description: 'Deepgram Nova - Real-time transcription',
      icon: FontAwesomeIcons.boltLightning,
      requiresApiKey: true,
      requestConfig: {
        'ws_url': 'wss://api.deepgram.com/v1/listen',
        'request_type': 'streaming',
        'headers': {
          'Authorization': 'Token YOUR_API_KEY',
        },
        'params': {
          'model': 'nova-2',
          'language': 'en',
          'smart_format': 'true',
          'interim_results': 'true',
          'punctuate': 'true',
          'encoding': 'linear16',
          'sample_rate': '16000',
        },
      },
      responseSchema: SttResponseSchema.deepgramLive,
    ),
    SttProvider.falai: SttProviderConfig(
      provider: SttProvider.falai,
      displayName: 'Fal.AI Wizper',
      description: 'Fal.AI Wizper - Cost effective',
      icon: FontAwesomeIcons.bolt,
      requiresApiKey: true,
      requestConfig: {
        'api_url': 'https://fal.run/fal-ai/wizper',
        'request_type': 'json_base64',
        'headers': {
          'Authorization': 'Key YOUR_API_KEY',
          'Content-Type': 'application/json',
        },
        'file_upload': {
          'file_upload_url': 'https://rest.alpha.fal.ai/storage/upload/initiate',
          'file_upload_headers': {
            'Authorization': 'Key YOUR_API_KEY',
            'Content-Type': 'application/json',
          },
          'file_upload_body': {
            'content_type': 'audio/wav',
            'file_name': 'audio.wav',
          },
        },
      },
      responseSchema: SttResponseSchema.falAI,
    ),
    SttProvider.gemini: SttProviderConfig(
      provider: SttProvider.gemini,
      displayName: 'Google Gemini',
      description: 'Google Gemini - Multimodal AI',
      icon: FontAwesomeIcons.google,
      requiresApiKey: true,
      requestConfig: {
        'api_url':
            'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=YOUR_API_KEY',
        'request_type': 'json_base64',
        'headers': {'Content-Type': 'application/json'},
      },
      responseSchema: SttResponseSchema.gemini,
    ),
    SttProvider.geminiLive: SttProviderConfig(
      provider: SttProvider.geminiLive,
      displayName: 'Gemini Live',
      description: 'Google Gemini - Real-time transcription',
      icon: FontAwesomeIcons.google,
      requiresApiKey: true,
      requestConfig: {
        'ws_url': 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent',
        'request_type': 'streaming',
        'headers': {},
        'params': {
          'key': 'YOUR_API_KEY',
        },
      },
      responseSchema: SttResponseSchema.geminiLive,
    ),
    SttProvider.localWhisper: SttProviderConfig(
      provider: SttProvider.localWhisper,
      displayName: 'Local Whisper',
      description: 'Self-hosted Whisper server',
      icon: FontAwesomeIcons.server,
      requestConfig: {
        'api_url': 'http://127.0.0.1:8080/inference',
        'request_type': 'multipart_form',
        'fields': {
          'temperature': '0.0',
          'temperature_inc': '0.2',
          'response_format': 'verbose_json',
        },
        'audio_field_name': 'file',
      },
      responseSchema: SttResponseSchema.openAI,
    ),
    SttProvider.custom: SttProviderConfig(
      provider: SttProvider.custom,
      displayName: 'Custom',
      description: 'Define your own STT endpoint (polling)',
      icon: FontAwesomeIcons.code,
      requestConfig: {
        'api_url': 'https://your-stt-api.com/transcribe',
        'request_type': 'multipart_form',
        'headers': {},
        'fields': {},
        'audio_field_name': 'audio',
      },
      responseSchema: SttResponseSchema(),
    ),
    SttProvider.customLive: SttProviderConfig(
      provider: SttProvider.customLive,
      displayName: 'Custom Live',
      description: 'Define your own real-time STT endpoint',
      icon: FontAwesomeIcons.codeBranch,
      requestConfig: {
        'ws_url': 'wss://your-stt-api.com/stream',
        'request_type': 'streaming',
        'headers': {},
        'params': {},
      },
      responseSchema: SttResponseSchema(),
    ),
  };

  static SttProviderConfig get(SttProvider provider) => _configs[provider]!;

  /// Safely get display name with fallback to raw string if provider not found
  static String getDisplayName(String? providerString) {
    if (providerString == null || providerString.isEmpty) {
      return 'Unknown';
    }
    try {
      final provider = SttProvider.fromString(providerString);
      return _configs[provider]?.displayName ?? providerString;
    } catch (e) {
      return providerString;
    }
  }

  static List<SttProviderConfig> get allProviders =>
      SttProvider.values.where((p) => p != SttProvider.omi).map((p) => get(p)).toList();

  Map<String, dynamic> getFullTemplateJson() => {
        'request': Map<String, dynamic>.from(requestConfig),
        'response_schema': responseSchema.toJson(),
      };

  Map<String, dynamic> getRequestConfigWithApiKey(String? apiKey) {
    if (apiKey == null || apiKey.isEmpty) {
      return Map<String, dynamic>.from(requestConfig);
    }

    final config = Map<String, dynamic>.from(requestConfig);
    final headers = Map<String, String>.from(config['headers'] ?? {});

    switch (provider) {
      case SttProvider.openai:
        headers['Authorization'] = 'Bearer $apiKey';
        break;
      case SttProvider.deepgram:
      case SttProvider.deepgramLive:
        headers['Authorization'] = 'Token $apiKey';
        break;
      case SttProvider.falai:
        headers['Authorization'] = 'Key $apiKey';
        if (config['file_upload'] != null) {
          final fileUpload = Map<String, dynamic>.from(config['file_upload']);
          final fileUploadHeaders = Map<String, String>.from(fileUpload['file_upload_headers'] ?? {});
          fileUploadHeaders['Authorization'] = 'Key $apiKey';
          fileUpload['file_upload_headers'] = fileUploadHeaders;
          config['file_upload'] = fileUpload;
        }
        break;
      case SttProvider.gemini:
        final url = config['api_url'] as String? ?? '';
        config['api_url'] = url.replaceAll('YOUR_API_KEY', apiKey);
        break;
      case SttProvider.geminiLive:
        if (config['params'] != null) {
          final params = Map<String, String>.from(config['params']);
          params['key'] = apiKey;
          config['params'] = params;
        }
        break;
      default:
        break;
    }

    config['headers'] = headers;
    return config;
  }

  static Map<String, dynamic> getLocalWhisperConfigWithHost(String host, int port) {
    final config = Map<String, dynamic>.from(get(SttProvider.localWhisper).requestConfig);
    config['api_url'] = 'http://$host:$port/inference';
    return config;
  }
}
