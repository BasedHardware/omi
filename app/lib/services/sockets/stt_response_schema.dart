class SttResponseSchema {
  final String? segmentsPath;
  final String textField;
  final String? startField;
  final String? endField;
  final String? speakerField;
  final String? speakerIdField;
  final String? confidenceField;
  final String? rawTextPath;
  final String? durationPath;
  final String? languagePath;
  final double defaultSegmentDuration;

  const SttResponseSchema({
    this.segmentsPath = 'segments',
    this.textField = 'text',
    this.startField = 'start',
    this.endField = 'end',
    this.speakerField,
    this.speakerIdField,
    this.confidenceField,
    this.rawTextPath = 'text',
    this.durationPath = 'duration',
    this.languagePath = 'language',
    this.defaultSegmentDuration = 5.0,
  });

  static const openAI = SttResponseSchema(
    segmentsPath: 'segments',
    textField: 'text',
    startField: 'start',
    endField: 'end',
    confidenceField: 'avg_logprob',
    rawTextPath: 'text',
    durationPath: 'duration',
    languagePath: 'language',
  );

  static const deepgram = SttResponseSchema(
    segmentsPath: 'results.channels[0].alternatives[0].words',
    textField: 'word',
    startField: 'start',
    endField: 'end',
    confidenceField: 'confidence',
    speakerField: 'speaker',
    rawTextPath: 'results.channels[0].alternatives[0].transcript',
    durationPath: 'metadata.duration',
    languagePath: 'metadata.language_code',
  );

  static const googleCloud = SttResponseSchema(
    segmentsPath: 'results[0].alternatives[0].words',
    textField: 'word',
    startField: 'startTime',
    endField: 'endTime',
    speakerField: 'speakerTag',
    confidenceField: 'confidence',
    rawTextPath: 'results[0].alternatives[0].transcript',
  );

  static const azure = SttResponseSchema(
    segmentsPath: 'recognizedPhrases',
    textField: 'nBest[0].display',
    startField: 'offsetInTicks',
    endField: 'durationInTicks',
    confidenceField: 'nBest[0].confidence',
    rawTextPath: 'combinedRecognizedPhrases[0].display',
    durationPath: 'duration',
  );

  static const simpleText = SttResponseSchema(
    segmentsPath: null,
    textField: 'text',
    rawTextPath: 'text',
  );

  static const falAI = SttResponseSchema(
    segmentsPath: 'chunks',
    textField: 'text',
    startField: 'timestamp[0]',
    endField: 'timestamp[1]',
    rawTextPath: 'text',
  );

  static const gemini = SttResponseSchema(
    segmentsPath: null,
    textField: 'text',
    rawTextPath: 'candidates[0].content.parts[0].text',
  );

  factory SttResponseSchema.fromJson(Map<String, dynamic> json) {
    return SttResponseSchema(
      segmentsPath: json['segments_path'] as String?,
      textField: json['text_field'] as String? ?? 'text',
      startField: json['start_field'] as String?,
      endField: json['end_field'] as String?,
      speakerField: json['speaker_field'] as String?,
      speakerIdField: json['speaker_id_field'] as String?,
      confidenceField: json['confidence_field'] as String?,
      rawTextPath: json['raw_text_path'] as String?,
      durationPath: json['duration_path'] as String?,
      languagePath: json['language_path'] as String?,
      defaultSegmentDuration: (json['default_segment_duration'] as num?)?.toDouble() ?? 5.0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'segments_path': segmentsPath,
      'text_field': textField,
      'start_field': startField,
      'end_field': endField,
      'speaker_field': speakerField,
      'speaker_id_field': speakerIdField,
      'confidence_field': confidenceField,
      'raw_text_path': rawTextPath,
      'duration_path': durationPath,
      'language_path': languagePath,
      'default_segment_duration': defaultSegmentDuration,
    };
  }
}

/// Centralized STT provider configuration
/// Contains both request config and response schema for each provider
class SttProviderConfig {
  final String id;
  final String displayName;
  final String description;
  final Map<String, dynamic> requestConfig;
  final SttResponseSchema responseSchema;

  const SttProviderConfig({
    required this.id,
    required this.displayName,
    required this.description,
    required this.requestConfig,
    required this.responseSchema,
  });

  static const openAI = SttProviderConfig(
    id: 'openai',
    displayName: 'OpenAI Whisper',
    description: 'OpenAI Whisper API - High accuracy',
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
  );

  static const deepgram = SttProviderConfig(
    id: 'deepgram',
    displayName: 'Deepgram',
    description: 'Deepgram Nova - Fast & accurate',
    requestConfig: {
      'api_url': 'https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true',
      'request_type': 'raw_binary',
      'headers': {
        'Authorization': 'Token YOUR_API_KEY',
        'Content-Type': 'audio/wav',
      },
    },
    responseSchema: SttResponseSchema.deepgram,
  );

  static const falAI = SttProviderConfig(
    id: 'falai',
    displayName: 'Fal.AI Wizper',
    description: 'Fal.AI Wizper - Cost effective',
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
  );

  static const gemini = SttProviderConfig(
    id: 'gemini',
    displayName: 'Google Gemini',
    description: 'Google Gemini - Multimodal AI',
    requestConfig: {
      'api_url': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=YOUR_API_KEY',
      'request_type': 'json_base64',
      'headers': {'Content-Type': 'application/json'},
    },
    responseSchema: SttResponseSchema.gemini,
  );

  static const whisperCpp = SttProviderConfig(
    id: 'whisper_cpp',
    displayName: 'Whisper.cpp',
    description: 'Self-hosted Whisper server',
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
  );

  static const custom = SttProviderConfig(
    id: 'custom',
    displayName: 'Custom',
    description: 'Define your own STT endpoint',
    requestConfig: {
      'api_url': 'https://your-stt-api.com/transcribe',
      'request_type': 'multipart_form',
      'headers': {},
      'fields': {},
      'audio_field_name': 'audio',
    },
    responseSchema: SttResponseSchema(),
  );

  /// Get provider config by ID
  static SttProviderConfig? getById(String id) {
    switch (id) {
      case 'openai':
        return openAI;
      case 'deepgram':
        return deepgram;
      case 'falai':
        return falAI;
      case 'gemini':
        return gemini;
      case 'whisper_cpp':
        return whisperCpp;
      case 'custom':
        return custom;
      default:
        return null;
    }
  }

  /// Get all available providers (excluding omi which is default)
  static List<SttProviderConfig> get allProviders => [
        openAI,
        deepgram,
        falAI,
        gemini,
        whisperCpp,
        custom,
      ];

  /// Get full template JSON for UI editing
  Map<String, dynamic> getFullTemplateJson() {
    return {
      'request': Map<String, dynamic>.from(requestConfig),
      'response_schema': responseSchema.toJson(),
    };
  }

  /// Create request config with API key injected
  Map<String, dynamic> getRequestConfigWithApiKey(String? apiKey) {
    if (apiKey == null || apiKey.isEmpty) {
      return Map<String, dynamic>.from(requestConfig);
    }

    final config = Map<String, dynamic>.from(requestConfig);
    final headers = Map<String, String>.from(config['headers'] ?? {});

    switch (id) {
      case 'openai':
        headers['Authorization'] = 'Bearer $apiKey';
        break;
      case 'deepgram':
        headers['Authorization'] = 'Token $apiKey';
        break;
      case 'falai':
        headers['Authorization'] = 'Key $apiKey';
        if (config['file_upload'] != null) {
          final fileUpload = Map<String, dynamic>.from(config['file_upload']);
          final fileUploadHeaders = Map<String, String>.from(fileUpload['file_upload_headers'] ?? {});
          fileUploadHeaders['Authorization'] = 'Key $apiKey';
          fileUpload['file_upload_headers'] = fileUploadHeaders;
          config['file_upload'] = fileUpload;
        }
        break;
      case 'gemini':
        final url = config['api_url'] as String? ?? '';
        config['api_url'] = url.replaceAll('YOUR_API_KEY', apiKey);
        break;
    }

    config['headers'] = headers;
    return config;
  }

  /// Create request config for whisper.cpp with host/port
  static Map<String, dynamic> getWhisperCppConfigWithHost(String host, int port) {
    final config = Map<String, dynamic>.from(whisperCpp.requestConfig);
    config['api_url'] = 'http://$host:$port/inference';
    return config;
  }
}

class JsonPathNavigator {
  static dynamic getValue(dynamic json, String? path) {
    if (path == null || path.isEmpty || json == null) {
      return null;
    }

    dynamic current = json;
    final segments = _parsePath(path);

    for (final segment in segments) {
      if (current == null) return null;

      if (segment.isArrayAccess) {
        if (segment.key.isNotEmpty) {
          if (current is Map) {
            current = current[segment.key];
          } else {
            return null;
          }
        }
        if (current is List && segment.index! < current.length) {
          current = current[segment.index!];
        } else {
          return null;
        }
      } else {
        if (current is Map) {
          current = current[segment.key];
        } else {
          return null;
        }
      }
    }

    return current;
  }

  static List<_PathSegment> _parsePath(String path) {
    final segments = <_PathSegment>[];
    final regex = RegExp(r'([^\.\[\]]+)|\[(\d+)\]');
    final matches = regex.allMatches(path);

    String? currentKey;
    for (final match in matches) {
      if (match.group(1) != null) {
        if (currentKey != null) {
          segments.add(_PathSegment(currentKey));
        }
        currentKey = match.group(1);
      } else if (match.group(2) != null) {
        final index = int.parse(match.group(2)!);
        segments.add(_PathSegment(currentKey ?? '', index: index));
        currentKey = null;
      }
    }

    if (currentKey != null) {
      segments.add(_PathSegment(currentKey));
    }

    return segments;
  }

  static String? getString(dynamic json, String? path) {
    final value = getValue(json, path);
    if (value == null) return null;
    return value.toString();
  }

  static double? getDouble(dynamic json, String? path) {
    final value = getValue(json, path);
    if (value == null) return null;
    if (value is num) return value.toDouble();
    if (value is String) {
      final cleaned = value.replaceAll('s', '');
      return double.tryParse(cleaned);
    }
    return null;
  }

  static int? getInt(dynamic json, String? path) {
    final value = getValue(json, path);
    if (value == null) return null;
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) return int.tryParse(value);
    return null;
  }

  static List? getList(dynamic json, String? path) {
    final value = getValue(json, path);
    if (value is List) return value;
    return null;
  }
}

class _PathSegment {
  final String key;
  final int? index;

  _PathSegment(this.key, {this.index});

  bool get isArrayAccess => index != null;
}
