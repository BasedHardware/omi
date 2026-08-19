import 'dart:convert';

import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/utils/logger.dart';

/// Controls which Custom STT data is forwarded to Omi.
///
/// [full] preserves the original composite behavior. [transcriptOnly] keeps
/// Omi text processing while withholding raw audio. [localOnly] keeps the
/// primary Custom STT path local to the app and does not create an Omi
/// secondary transcription socket.
enum SttPrivacyPolicy { full, transcriptOnly, localOnly }

SttPrivacyPolicy? _parsePrivacyPolicy(dynamic value) {
  if (value is! String) return null;
  for (final policy in SttPrivacyPolicy.values) {
    if (policy.name == value) return policy;
  }
  return null;
}

/// Migrate persisted configs without changing the established #10447 default.
/// An explicit but invalid new policy fails privacy-closed to
/// [SttPrivacyPolicy.localOnly] and does not consult the legacy boolean.
SttPrivacyPolicy _migratePrivacyPolicy(Map<String, dynamic> json) {
  if (json.containsKey('privacy_policy')) {
    return _parsePrivacyPolicy(json['privacy_policy']) ?? SttPrivacyPolicy.localOnly;
  }
  if (json['send_raw_audio_to_omi'] == false) return SttPrivacyPolicy.transcriptOnly;
  return SttPrivacyPolicy.full;
}

class CustomSttConfig {
  final SttProvider provider;
  final String? apiKey;
  final String? language;
  final String? model;
  final String? url;
  final String? host;
  final int? port;
  final String? requestType;
  final Map<String, String>? headers;
  final Map<String, String>? params;
  final String? audioFieldName;
  final Map<String, dynamic>? schemaJson;
  final SttPrivacyPolicy privacyPolicy;

  const CustomSttConfig({
    required this.provider,
    this.apiKey,
    this.language,
    this.model,
    this.url,
    this.host,
    this.port,
    this.requestType,
    this.headers,
    this.params,
    this.audioFieldName,
    this.schemaJson,
    this.privacyPolicy = SttPrivacyPolicy.full,
  });

  /// Determine if live/streaming based on request_type
  String get effectiveRequestType => requestType ?? providerConfig.requestType;
  bool get isLive => SttRequestType.isLive(effectiveRequestType);
  bool get isPolling => SttRequestType.isPolling(effectiveRequestType);

  bool get isEnabled => provider != SttProvider.omi;

  /// Whether raw audio frames are forwarded to the Omi secondary socket.
  bool get forwardsRawAudioToOmi => privacyPolicy == SttPrivacyPolicy.full;

  /// Whether the Omi secondary transcription socket must not be constructed.
  bool get isLocalOnlyPolicy => privacyPolicy == SttPrivacyPolicy.localOnly;

  SttProviderConfig get providerConfig => SttProviderConfig.get(provider);

  SttResponseSchema get schema {
    if (schemaJson != null) {
      return SttResponseSchema.fromJson(schemaJson!);
    }
    return providerConfig.responseSchema;
  }

  /// Get the effective language (user-selected or provider default)
  String get effectiveLanguage => language ?? providerConfig.defaultLanguage;

  /// Get the effective model (user-selected or provider default)
  String get effectiveModel => model ?? providerConfig.defaultModel;

  /// Get effective URL (custom or provider default)
  String get effectiveUrl {
    if (url != null && url!.isNotEmpty) return url!;
    final config = providerConfig.buildRequestConfig(
      apiKey: apiKey,
      language: language,
      model: model,
      host: host,
      port: port,
    );
    return config['url'] ?? '';
  }

  /// Build request config with all settings applied
  /// Merges user customizations with provider defaults (user values win)
  Map<String, dynamic> get requestConfig {
    // Get provider defaults (works for all providers including custom)
    final config = providerConfig.buildRequestConfig(
      apiKey: apiKey,
      language: language,
      model: model,
      host: host,
      port: port,
    );

    final defaultParams = Map<String, String>.from(config['params'] ?? {});
    final defaultHeaders = Map<String, String>.from(config['headers'] ?? {});

    // Merge user params with defaults (user values override defaults)
    if (params != null && params!.isNotEmpty) {
      config['params'] = {...defaultParams, ...params!};
    }

    // Merge user headers with defaults (user values override defaults)
    if (headers != null && headers!.isNotEmpty) {
      config['headers'] = {...defaultHeaders, ...headers!};
    }

    // Apply explicit overrides
    if (url != null && url!.isNotEmpty) config['url'] = url;
    if (requestType != null) config['request_type'] = requestType;
    if (audioFieldName != null) config['audio_field_name'] = audioFieldName;

    return config;
  }

  String get sttConfigId {
    if (!isEnabled) return 'omi:default';

    final configData = {
      'api_key': apiKey,
      'language': language,
      'model': model,
      'url': url,
      'host': host,
      'port': port,
      'request_type': requestType,
      'headers': headers,
      'params': params,
      'privacy_policy': privacyPolicy.name,
    };

    final jsonStr = jsonEncode(configData);
    final hashValue = jsonStr.hashCode.abs();
    final hash = hashValue.toRadixString(16).padLeft(8, '0').substring(0, 8);
    Logger.debug('${provider.name}:$hash');
    return '${provider.name}:$hash';
  }

  Map<String, dynamic> toJson() => {
        'provider': provider.name,
        'api_key': apiKey,
        'language': language,
        'model': model,
        'url': url,
        'host': host,
        'port': port,
        'request_type': requestType,
        'headers': headers,
        'params': params,
        'audio_field_name': audioFieldName,
        'schema': schemaJson,
        'privacy_policy': privacyPolicy.name,
        // Keep the legacy field for older clients. The typed policy is
        // authoritative when both fields are present.
        'send_raw_audio_to_omi': forwardsRawAudioToOmi,
      };

  factory CustomSttConfig.fromJson(Map<String, dynamic> json) {
    // Safely cast maps to Map<String, String> by converting all values to strings
    Map<String, String>? safeStringMap(dynamic value) {
      if (value == null) return null;
      if (value is Map) {
        return value.map((k, v) => MapEntry(k.toString(), v?.toString() ?? ''));
      }
      return null;
    }

    final rawProvider = json['provider'];
    if (rawProvider is! String) {
      throw const FormatException('Custom STT provider is missing or malformed');
    }
    final provider = SttProvider.tryFromString(rawProvider);
    if (provider == null) {
      throw FormatException('Unknown Custom STT provider: $rawProvider');
    }

    return CustomSttConfig(
      provider: provider,
      apiKey: json['api_key'],
      language: json['language'],
      model: json['model'],
      url: json['url'],
      host: json['host'],
      port: json['port'],
      requestType: json['request_type'],
      headers: safeStringMap(json['headers']),
      params: safeStringMap(json['params']),
      audioFieldName: json['audio_field_name'],
      schemaJson: json['schema'] != null ? Map<String, dynamic>.from(json['schema']) : null,
      privacyPolicy: _migratePrivacyPolicy(json),
    );
  }

  static const defaultConfig = CustomSttConfig(provider: SttProvider.omi);

  /// Used only when a persisted Custom STT blob cannot be decoded. A corrupt
  /// preference must not silently restore Omi audio egress.
  static const privacySafeFallbackConfig = CustomSttConfig(
    provider: SttProvider.omi,
    privacyPolicy: SttPrivacyPolicy.localOnly,
  );

  /// Copy with new values
  CustomSttConfig copyWith({
    SttProvider? provider,
    String? apiKey,
    String? language,
    String? model,
    String? url,
    String? host,
    int? port,
    String? requestType,
    Map<String, String>? headers,
    Map<String, String>? params,
    String? audioFieldName,
    Map<String, dynamic>? schemaJson,
    SttPrivacyPolicy? privacyPolicy,
  }) {
    return CustomSttConfig(
      provider: provider ?? this.provider,
      apiKey: apiKey ?? this.apiKey,
      language: language ?? this.language,
      model: model ?? this.model,
      url: url ?? this.url,
      host: host ?? this.host,
      port: port ?? this.port,
      requestType: requestType ?? this.requestType,
      headers: headers ?? this.headers,
      params: params ?? this.params,
      audioFieldName: audioFieldName ?? this.audioFieldName,
      schemaJson: schemaJson ?? this.schemaJson,
      privacyPolicy: privacyPolicy ?? this.privacyPolicy,
    );
  }

  static Map<String, dynamic> getFullTemplateJson(SttProvider provider) {
    return SttProviderConfig.get(provider).getFullTemplateJson();
  }
}
