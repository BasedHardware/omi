import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';

class AssistantVoice {
  const AssistantVoice({required this.id, required this.name});

  final String id;
  final String name;

  factory AssistantVoice.fromJson(Map<String, dynamic> json) {
    final id = json['id'];
    final name = json['name'];
    if (id is! String || id.isEmpty || name is! String || name.isEmpty) {
      throw const FormatException('invalid assistant voice');
    }
    return AssistantVoice(id: id, name: name);
  }
}

class AssistantVoiceCatalog {
  const AssistantVoiceCatalog({required this.voices, required this.defaultVoiceId});

  final List<AssistantVoice> voices;
  final String defaultVoiceId;

  factory AssistantVoiceCatalog.fromJson(Map<String, dynamic> json) {
    final voices = json['voices'];
    final defaultVoiceId = json['default_voice_id'];
    if (voices is! List || voices.isEmpty || defaultVoiceId is! String || defaultVoiceId.isEmpty) {
      throw const FormatException('invalid voice catalog');
    }
    final deduped = <String, AssistantVoice>{};
    for (final row in voices) {
      if (row is! Map) throw const FormatException('invalid voice catalog');
      final voice = AssistantVoice.fromJson(Map<String, dynamic>.from(row));
      deduped[voice.id] = voice;
    }
    if (!deduped.containsKey(defaultVoiceId)) {
      throw const FormatException('invalid voice catalog');
    }
    return AssistantVoiceCatalog(
      voices: deduped.values.toList(growable: false),
      defaultVoiceId: defaultVoiceId,
    );
  }
}

class AssistantVoicePreference {
  const AssistantVoicePreference(this.voiceId);

  final String voiceId;

  factory AssistantVoicePreference.fromJson(Map<String, dynamic> json) {
    final voiceId = json['voice_id'];
    if (voiceId is! String || voiceId.isEmpty) {
      throw const FormatException('invalid voice preference');
    }
    return AssistantVoicePreference(voiceId);
  }
}

class AssistantVoicesApi {
  const AssistantVoicesApi({this.send});

  final ApiSend? send;

  Future<ApiResult<AssistantVoiceCatalog>> getCatalog() => executeApi(
        request: ApiRequest(url: '${Env.apiBaseUrl}v1/tts/voices', method: 'GET'),
        send: send,
        decode: (body) {
          final row = jsonDecode(body);
          if (row is! Map<String, dynamic>) throw const FormatException('invalid voice catalog');
          return AssistantVoiceCatalog.fromJson(row);
        },
      );

  Future<ApiResult<AssistantVoicePreference>> getPreference() => executeApi(
        request: ApiRequest(url: '${Env.apiBaseUrl}v1/users/voice', method: 'GET'),
        send: send,
        decode: (body) {
          final row = jsonDecode(body);
          if (row is! Map<String, dynamic>) throw const FormatException('invalid voice preference');
          return AssistantVoicePreference.fromJson(row);
        },
      );

  Future<ApiResult<AssistantVoicePreference>> setPreference(String voiceId) => executeApi(
        request: ApiRequest(
          url: '${Env.apiBaseUrl}v1/users/voice',
          method: 'PATCH',
          body: jsonEncode({'voice_id': voiceId}),
        ),
        send: send,
        decode: (body) {
          final row = jsonDecode(body);
          if (row is! Map<String, dynamic>) throw const FormatException('invalid voice preference');
          return AssistantVoicePreference.fromJson(row);
        },
      );
}
