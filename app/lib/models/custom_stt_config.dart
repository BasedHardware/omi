import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/stt_response_schema.dart';

class CustomSttConfig {
  final SttProvider provider;
  final String? apiKey;
  final String? apiUrl;
  final String? host;
  final int? port;
  final Map<String, String>? headers;
  final Map<String, String>? fields;
  final String? audioFieldName;
  final String? requestType;
  final Map<String, dynamic>? schemaJson;
  final Map<String, dynamic>? fileUploadConfig;

  const CustomSttConfig({
    required this.provider,
    this.apiKey,
    this.apiUrl,
    this.host,
    this.port,
    this.headers,
    this.fields,
    this.audioFieldName,
    this.requestType,
    this.schemaJson,
    this.fileUploadConfig,
  });

  bool get isEnabled => provider != SttProvider.omi;

  SttProviderConfig get providerConfig => SttProviderConfig.get(provider);

  SttResponseSchema get schema {
    if (schemaJson != null) {
      return SttResponseSchema.fromJson(schemaJson!);
    }
    return providerConfig.responseSchema;
  }

  String get sttConfigId {
    if (!isEnabled) return 'omi:default';

    final configData = {
      'api_key': apiKey,
      'api_url': apiUrl,
      'host': host,
      'port': port,
      'headers': headers,
      'fields': fields,
      'audio_field_name': audioFieldName,
      'request_type': requestType,
      'schema': schemaJson,
      'file_upload_config': fileUploadConfig,
    };

    final jsonStr = jsonEncode(configData);
    final hashValue = jsonStr.hashCode.abs();
    final hash = hashValue.toRadixString(16).padLeft(8, '0').substring(0, 8);
    debugPrint('${provider.name}:$hash');
    return '${provider.name}:$hash';
  }

  Map<String, dynamic> toJson() => {
        'provider': provider.name,
        'api_key': apiKey,
        'api_url': apiUrl,
        'host': host,
        'port': port,
        'headers': headers,
        'fields': fields,
        'audio_field_name': audioFieldName,
        'request_type': requestType,
        'schema': schemaJson,
        'file_upload_config': fileUploadConfig,
      };

  factory CustomSttConfig.fromJson(Map<String, dynamic> json) {
    return CustomSttConfig(
      provider: SttProvider.fromString(json['provider'] ?? 'omi'),
      apiKey: json['api_key'],
      apiUrl: json['api_url'],
      host: json['host'],
      port: json['port'],
      headers: json['headers'] != null ? Map<String, String>.from(json['headers']) : null,
      fields: json['fields'] != null ? Map<String, String>.from(json['fields']) : null,
      audioFieldName: json['audio_field_name'],
      requestType: json['request_type'],
      schemaJson: json['schema'] != null ? Map<String, dynamic>.from(json['schema']) : null,
      fileUploadConfig:
          json['file_upload_config'] != null ? Map<String, dynamic>.from(json['file_upload_config']) : null,
    );
  }

  static const defaultConfig = CustomSttConfig(provider: SttProvider.omi);

  static Map<String, dynamic> getFullTemplateJson(SttProvider provider) {
    return SttProviderConfig.get(provider).getFullTemplateJson();
  }
}
