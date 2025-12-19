import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/models/stt_response_schema.dart';

enum SttProvider {
  omi,
  openai,
  openaiDiarize,
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

/// Request types determine how audio is sent and whether it's streaming
class SttRequestType {
  static const String multipartForm = 'multipart_form';
  static const String rawBinary = 'raw_binary';
  static const String jsonBase64 = 'json_base64';
  static const String streaming = 'streaming';

  static bool isLive(String? type) => type == streaming;
  static bool isPolling(String? type) => !isLive(type);
}

/// Common languages supported by most STT providers
class SttLanguages {
  static const Map<String, String> common = {
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'it': 'Italian',
    'pt': 'Portuguese',
    'nl': 'Dutch',
    'ja': 'Japanese',
    'ko': 'Korean',
    'zh': 'Chinese',
    'ar': 'Arabic',
    'hi': 'Hindi',
    'ru': 'Russian',
    'pl': 'Polish',
    'tr': 'Turkish',
    'vi': 'Vietnamese',
    'th': 'Thai',
    'id': 'Indonesian',
    'multi': 'Auto-detect',
  };

  static const List<String> whisperSupported = [
    'en',
    'es',
    'fr',
    'de',
    'it',
    'pt',
    'nl',
    'ja',
    'ko',
    'zh',
    'ar',
    'hi',
    'ru',
    'pl',
    'tr',
    'vi',
    'th',
    'id'
  ];

  static const List<String> deepgramSupported = [
    'multi',
    'en',
    'es',
    'fr',
    'de',
    'it',
    'pt',
    'nl',
    'ja',
    'ko',
    'zh',
    'hi',
    'ru',
    'pl',
    'tr',
    'id'
  ];

  static const List<String> geminiSupported = ['en', 'es', 'fr', 'de', 'it', 'pt', 'ja', 'ko', 'zh', 'ar', 'hi', 'ru'];
}

class SttProviderConfig {
  final SttProvider provider;
  final String displayName;
  final String description;
  final IconData icon;
  final bool requiresApiKey;
  final String requestType;
  final SttResponseSchema responseSchema;
  final List<String> supportedLanguages;
  final List<String> supportedModels;
  final String defaultLanguage;
  final String defaultModel;
  final String? apiKeyUrl;
  final String? docsUrl;

  const SttProviderConfig({
    required this.provider,
    required this.displayName,
    required this.description,
    required this.icon,
    this.requiresApiKey = false,
    this.requestType = SttRequestType.multipartForm,
    required this.responseSchema,
    this.supportedLanguages = const ['en'],
    this.supportedModels = const [],
    this.defaultLanguage = 'en',
    this.defaultModel = '',
    this.apiKeyUrl,
    this.docsUrl,
  });

  bool get isLive => SttRequestType.isLive(requestType);
  bool get isPolling => SttRequestType.isPolling(requestType);

  static final _configs = <SttProvider, SttProviderConfig>{
    SttProvider.omi: SttProviderConfig(
      provider: SttProvider.omi,
      displayName: 'Omi',
      description: 'Omi\'s optimized transcription service',
      icon: FontAwesomeIcons.robot,
      requestType: SttRequestType.streaming,
      responseSchema: const SttResponseSchema(),
    ),
    SttProvider.openai: SttProviderConfig(
      provider: SttProvider.openai,
      displayName: 'OpenAI Whisper',
      description: 'OpenAI Whisper API - High accuracy',
      icon: FontAwesomeIcons.brain,
      requiresApiKey: true,
      requestType: SttRequestType.multipartForm,
      supportedLanguages: SttLanguages.whisperSupported,
      supportedModels: const ['whisper-1'],
      defaultLanguage: 'en',
      defaultModel: 'whisper-1',
      responseSchema: SttResponseSchema.openAI,
      apiKeyUrl: 'https://platform.openai.com/api-keys',
      docsUrl: 'https://platform.openai.com/docs/guides/speech-to-text',
    ),
    SttProvider.openaiDiarize: SttProviderConfig(
      provider: SttProvider.openaiDiarize,
      displayName: 'OpenAI GPT-4o Transcribe Diarize',
      description: 'GPT-4o Transcribe with speaker diarization',
      icon: FontAwesomeIcons.userGroup,
      requiresApiKey: true,
      requestType: SttRequestType.multipartForm,
      supportedLanguages: SttLanguages.whisperSupported,
      supportedModels: const ['gpt-4o-transcribe-diarize'],
      defaultLanguage: 'en',
      defaultModel: 'gpt-4o-transcribe-diarize',
      responseSchema: SttResponseSchema.openAIDiarize,
      apiKeyUrl: 'https://platform.openai.com/api-keys',
      docsUrl: 'https://platform.openai.com/docs/models/gpt-4o-transcribe-diarize',
    ),
    SttProvider.deepgram: SttProviderConfig(
      provider: SttProvider.deepgram,
      displayName: 'Deepgram',
      description: 'Deepgram Nova - Fast & accurate (polling)',
      icon: FontAwesomeIcons.waveSquare,
      requiresApiKey: true,
      requestType: SttRequestType.rawBinary,
      supportedLanguages: SttLanguages.deepgramSupported,
      supportedModels: const ['nova-3', 'nova-2'],
      defaultLanguage: 'multi',
      defaultModel: 'nova-3',
      responseSchema: SttResponseSchema.deepgram,
      apiKeyUrl: 'https://console.deepgram.com/',
      docsUrl: 'https://developers.deepgram.com/docs/models-languages-overview',
    ),
    SttProvider.deepgramLive: SttProviderConfig(
      provider: SttProvider.deepgramLive,
      displayName: 'Deepgram',
      description: 'Deepgram Nova - Real-time streaming',
      icon: FontAwesomeIcons.boltLightning,
      requiresApiKey: true,
      requestType: SttRequestType.streaming,
      supportedLanguages: SttLanguages.deepgramSupported,
      supportedModels: const ['nova-3', 'nova-2'],
      defaultLanguage: 'multi',
      defaultModel: 'nova-3',
      responseSchema: SttResponseSchema.deepgramLive,
      apiKeyUrl: 'https://console.deepgram.com/',
      docsUrl: 'https://developers.deepgram.com/docs/models-languages-overview',
    ),
    SttProvider.falai: SttProviderConfig(
      provider: SttProvider.falai,
      displayName: 'Fal.AI Wizper',
      description: 'Fal.AI Wizper - Cost effective',
      icon: FontAwesomeIcons.bolt,
      requiresApiKey: true,
      requestType: SttRequestType.jsonBase64,
      supportedLanguages: SttLanguages.whisperSupported,
      defaultLanguage: 'en',
      responseSchema: SttResponseSchema.falAI,
      apiKeyUrl: 'https://fal.ai/dashboard/keys',
      docsUrl: 'https://fal.ai/models/fal-ai/wizper',
    ),
    SttProvider.gemini: SttProviderConfig(
      provider: SttProvider.gemini,
      displayName: 'Google Gemini',
      description: 'Google Gemini - Multimodal AI',
      icon: FontAwesomeIcons.google,
      requiresApiKey: true,
      requestType: SttRequestType.jsonBase64,
      supportedLanguages: SttLanguages.geminiSupported,
      supportedModels: const ['gemini-2.5-flash', 'gemini-2.5-pro'],
      defaultLanguage: 'en',
      defaultModel: 'gemini-2.0-flash',
      responseSchema: SttResponseSchema.gemini,
      apiKeyUrl: 'https://aistudio.google.com/apikey',
      docsUrl: 'https://ai.google.dev/gemini-api/docs/models/gemini',
    ),
    SttProvider.geminiLive: SttProviderConfig(
      provider: SttProvider.geminiLive,
      displayName: 'Google Gemini',
      description: 'Google Gemini - Real-time streaming',
      icon: FontAwesomeIcons.google,
      requiresApiKey: true,
      requestType: SttRequestType.streaming,
      supportedLanguages: SttLanguages.geminiSupported,
      supportedModels: const ['gemini-2.5-flash-native-audio-preview-12-2025'],
      defaultLanguage: 'en',
      defaultModel: 'gemini-2.5-flash-native-audio-preview-12-2025',
      responseSchema: SttResponseSchema.geminiLive,
      apiKeyUrl: 'https://aistudio.google.com/apikey',
      docsUrl: 'https://ai.google.dev/gemini-api/docs/models/gemini',
    ),
    SttProvider.localWhisper: SttProviderConfig(
      provider: SttProvider.localWhisper,
      displayName: 'Local Whisper',
      description: 'Self-hosted Whisper server',
      icon: FontAwesomeIcons.server,
      requestType: SttRequestType.multipartForm,
      supportedLanguages: SttLanguages.whisperSupported,
      defaultLanguage: 'en',
      responseSchema: SttResponseSchema.openAI,
      docsUrl: 'https://github.com/openai/whisper',
    ),
    SttProvider.custom: SttProviderConfig(
      provider: SttProvider.custom,
      displayName: 'Custom',
      description: 'Define your own STT endpoint (polling)',
      icon: FontAwesomeIcons.code,
      requestType: SttRequestType.multipartForm,
      supportedLanguages: SttLanguages.whisperSupported,
      defaultLanguage: 'en',
      responseSchema: SttResponseSchema.openAI,
    ),
    SttProvider.customLive: SttProviderConfig(
      provider: SttProvider.customLive,
      displayName: 'Custom',
      description: 'Define your own real-time STT endpoint',
      icon: FontAwesomeIcons.codeBranch,
      requestType: SttRequestType.streaming,
      supportedLanguages: SttLanguages.whisperSupported,
      defaultLanguage: 'en',
      responseSchema: SttResponseSchema.openAI,
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

  static const _visibleProviders = [
    SttProvider.openai,
    SttProvider.openaiDiarize,
    SttProvider.deepgramLive,
    SttProvider.geminiLive,
    SttProvider.localWhisper,
    SttProvider.customLive,
  ];

  static List<SttProviderConfig> get allProviders => _visibleProviders.map((p) => get(p)).toList();

  /// Template names that are live/streaming
  static const Set<String> liveRequestTemplates = {'Deepgram', 'Google Gemini'};

  /// Available request config templates for custom STT configuration
  static Map<String, Map<String, dynamic>> get requestTemplates => {
        'OpenAI': get(SttProvider.openai).buildRequestConfig(
          apiKey: 'YOUR_API_KEY',
          language: 'en',
          model: 'whisper-1',
        ),
        'Deepgram': get(SttProvider.deepgramLive).buildRequestConfig(
          apiKey: 'YOUR_API_KEY',
          language: 'multi',
          model: 'nova-3',
        ),
        'Fal.AI': get(SttProvider.falai).buildRequestConfig(
          apiKey: 'YOUR_API_KEY',
          language: 'en',
        ),
        'Google Gemini': get(SttProvider.geminiLive).buildRequestConfig(
          apiKey: 'YOUR_API_KEY',
          language: 'en',
          model: 'gemini-2.5-flash',
        ),
        'Whisper': get(SttProvider.localWhisper).buildRequestConfig(
          language: 'en',
        ),
      };

  Map<String, dynamic> getFullTemplateJson() => {
        'request_type': requestType,
        'response_schema': responseSchema.toJson(),
      };

  /// Build complete request config with API key, language, and model
  /// Returns unified structure: url, request_type, headers, params, audio_field_name
  Map<String, dynamic> buildRequestConfig({
    String? apiKey,
    String? language,
    String? model,
    String? host,
    int? port,
  }) {
    final config = <String, dynamic>{};
    final lang = language ?? defaultLanguage;
    final mdl = model ?? defaultModel;

    config['request_type'] = requestType;

    switch (provider) {
      case SttProvider.openai:
        config['url'] = 'https://api.openai.com/v1/audio/transcriptions';
        config['audio_field_name'] = 'file';
        config['headers'] = {'Authorization': 'Bearer ${apiKey ?? ''}'};
        config['params'] = {
          'model': mdl.isNotEmpty ? mdl : 'whisper-1',
          'language': lang,
          'response_format': 'verbose_json',
          'timestamp_granularities[]': 'segment',
        };
        break;

      case SttProvider.openaiDiarize:
        config['url'] = 'https://api.openai.com/v1/audio/transcriptions';
        config['audio_field_name'] = 'file';
        config['headers'] = {'Authorization': 'Bearer ${apiKey ?? ''}'};
        config['params'] = {
          'model': mdl.isNotEmpty ? mdl : 'gpt-4o-transcribe-diarize',
          'language': lang,
          'response_format': 'diarized_json',
          'chunking_strategy': 'auto',
        };
        break;

      case SttProvider.deepgram:
        config['url'] = 'https://api.deepgram.com/v1/listen';
        config['headers'] = {
          'Authorization': 'Token ${apiKey ?? ''}',
          'Content-Type': 'audio/wav',
        };
        config['params'] = {
          'model': mdl.isNotEmpty ? mdl : 'nova-3',
          'language': lang,
          'smart_format': 'true',
          'diarize': 'true',
        };
        break;

      case SttProvider.deepgramLive:
        config['url'] = 'wss://api.deepgram.com/v1/listen';
        config['headers'] = {'Authorization': 'Token ${apiKey ?? ''}'};
        config['params'] = {
          'model': mdl.isNotEmpty ? mdl : 'nova-3',
          'language': lang,
          'smart_format': 'true',
          'punctuate': 'true',
          'diarize': 'true',
          'interim_results': 'false',
          'no_delay': 'true',
          'endpointing': '300',
          'encoding': 'linear16',
          'sample_rate': '16000',
          'channels': '1',
        };
        break;

      case SttProvider.falai:
        config['url'] = 'https://fal.run/fal-ai/wizper';
        config['headers'] = {
          'Authorization': 'Key ${apiKey ?? ''}',
          'Content-Type': 'application/json',
        };
        config['params'] = {'language': lang};
        break;

      case SttProvider.gemini:
        final modelName = mdl.isNotEmpty ? mdl : 'gemini-2.0-flash';
        config['url'] =
            'https://generativelanguage.googleapis.com/v1beta/models/$modelName:generateContent?key=${apiKey ?? ''}';
        config['headers'] = {'Content-Type': 'application/json'};
        config['params'] = {'language': lang};
        break;

      case SttProvider.geminiLive:
        config['url'] =
            'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key=${apiKey ?? ''}';
        config['params'] = {
          'model': mdl.isNotEmpty ? mdl : 'gemini-2.5-flash-native-audio-preview-12-2025',
          'language': lang,
        };
        break;

      case SttProvider.localWhisper:
        final h = host ?? '127.0.0.1';
        final p = port ?? 8080;
        config['url'] = 'http://$h:$p/inference';
        config['audio_field_name'] = 'file';
        config['params'] = {
          'language': lang,
          'temperature': '0.0',
          'temperature_inc': '0.2',
          'response_format': 'verbose_json',
        };
        break;

      case SttProvider.custom:
        config['url'] = 'http://127.0.0.1:8080/inference';
        config['audio_field_name'] = 'file';
        config['params'] = {'language': lang};
        break;

      case SttProvider.customLive:
        config['url'] = 'wss://your-stt-api.com/stream';
        config['params'] = {'language': lang};
        break;

      default:
        return {};
    }

    return config;
  }
}
