import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/misc_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

/// A selectable assistant voice from the served catalog.
class AssistantVoice {
  const AssistantVoice({required this.id, required this.name});

  final String id;
  final String name;
}

class AssistantVoiceCatalog {
  const AssistantVoiceCatalog({required this.voices, required this.defaultVoiceId});

  final List<AssistantVoice> voices;
  final String defaultVoiceId;

  static AssistantVoiceCatalog fromGeneratedWireJson(wire.GeneratedTtsVoiceCatalog generated) {
    final deduped = <String, AssistantVoice>{
      for (final voice in generated.voices) voice.id: AssistantVoice(id: voice.id, name: voice.name),
    };
    if (deduped.isEmpty || !deduped.containsKey(generated.defaultVoiceId)) {
      throw const FormatException('invalid voice catalog');
    }
    return AssistantVoiceCatalog(
      voices: deduped.values.toList(growable: false),
      defaultVoiceId: generated.defaultVoiceId,
    );
  }
}

class AssistantVoicePreference {
  const AssistantVoicePreference(this.voiceId);

  final String voiceId;

  static AssistantVoicePreference fromGeneratedWireJson(wire.GeneratedAssistantVoicePreference generated) {
    if (generated.voiceId.isEmpty) {
      throw const FormatException('invalid voice preference');
    }
    return AssistantVoicePreference(generated.voiceId);
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
          return AssistantVoiceCatalog.fromGeneratedWireJson(wire.GeneratedTtsVoiceCatalog.fromJson(row));
        },
      );

  Future<ApiResult<AssistantVoicePreference>> getPreference() => executeApi(
        request: ApiRequest(url: '${Env.apiBaseUrl}v1/users/voice', method: 'GET'),
        send: send,
        decode: (body) {
          final row = jsonDecode(body);
          if (row is! Map<String, dynamic>) throw const FormatException('invalid voice preference');
          return AssistantVoicePreference.fromGeneratedWireJson(wire.GeneratedAssistantVoicePreference.fromJson(row));
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
          return AssistantVoicePreference.fromGeneratedWireJson(wire.GeneratedAssistantVoicePreference.fromJson(row));
        },
      );
}
