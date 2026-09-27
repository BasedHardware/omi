import 'dart:convert';
import 'dart:typed_data';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

/// Speaker tag prompts ("Is this you?" / "Who is this?") and voice-profile preferences.
/// Every call returns a typed [ApiResult]; callers decide what an outage means.

Map<String, dynamic> _object(String body) {
  final decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
  return decoded;
}

Future<ApiResult<wire.GeneratedSpeakerTagPromptsResponse>> getSpeakerTagPrompts() => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/speaker-tag-prompts', method: 'GET'),
      decode: (body) => wire.GeneratedSpeakerTagPromptsResponse.fromJson(_object(body)),
    );

Future<ApiResult<bool>> markSpeakerTagPromptsShown(List<String> promptIds) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/speaker-tag-prompts/shown',
        method: 'POST',
        body: jsonEncode(wire.GeneratedSpeakerTagPromptsShownRequest(promptIds: promptIds).toJson()),
      ),
      decode: (body) => wire.GeneratedSpeakerTagPromptsShownResponse.fromJson(_object(body)).firstTime,
    );

Future<ApiResult<void>> dismissSpeakerTagPrompts() => executeApi<void>(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/speaker-tag-prompts/dismiss', method: 'POST'),
      decode: (_) {},
    );

Future<ApiResult<wire.GeneratedSpeakerTagPromptAnswerResponse>> answerSpeakerTagPrompt(
  wire.GeneratedSpeakerTagPromptAnswerRequest request,
) =>
    executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/speaker-tag-prompts/answer',
        method: 'POST',
        body: jsonEncode(request.toJson()),
      ),
      decode: (body) => wire.GeneratedSpeakerTagPromptAnswerResponse.fromJson(_object(body)),
    );

/// WAV bytes for a short window of the user's own stored conversation audio.
Future<ApiResult<Uint8List>> getSpeakerTagPromptClip({
  required String conversationId,
  required double start,
  required double end,
}) {
  final query = Uri(
    queryParameters: {
      'conversation_id': conversationId,
      'start': start.toStringAsFixed(3),
      'end': end.toStringAsFixed(3),
    },
  ).query;
  return executeApi(
    request: ApiRequest(url: '${Env.apiBaseUrl}v1/speaker-tag-prompts/clip?$query', method: 'GET'),
    decode: (body) {
      final decoded = jsonDecode(body);
      if (decoded is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
      return base64Decode(wire.GeneratedSpeakerTagPromptClip.fromJson(decoded).audioBase64);
    },
  );
}

Future<ApiResult<wire.GeneratedVoiceProfileSettings>> getVoiceProfileSettings() => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/users/voice-profile-settings', method: 'GET'),
      decode: (body) => wire.GeneratedVoiceProfileSettings.fromJson(_object(body)),
    );

Future<ApiResult<wire.GeneratedVoiceProfileSettings>> updateVoiceProfileSettings({
  bool? speakerTagPromptsEnabled,
  bool? saveOtherVoiceProfiles,
  required String source,
}) {
  final body = <String, dynamic>{'source': source};
  if (speakerTagPromptsEnabled != null) body['speaker_tag_prompts_enabled'] = speakerTagPromptsEnabled;
  if (saveOtherVoiceProfiles != null) body['save_other_voice_profiles'] = saveOtherVoiceProfiles;
  return executeApi(
    request:
        ApiRequest(url: '${Env.apiBaseUrl}v1/users/voice-profile-settings', method: 'PATCH', body: jsonEncode(body)),
    decode: (body) {
      final decoded = jsonDecode(body);
      if (decoded is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
      return wire.GeneratedVoiceProfileSettings.fromJson(decoded);
    },
  );
}
