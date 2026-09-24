import 'dart:convert';
import 'dart:typed_data';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// Speaker tag prompts ("Is this you?" / "Who is this?") and voice-profile preferences.

Future<GeneratedSpeakerTagPromptsResponse?> getSpeakerTagPrompts() async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speaker-tag-prompts',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200) return null;
  try {
    return GeneratedSpeakerTagPromptsResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  } catch (error) {
    Logger.debug('getSpeakerTagPrompts decode failed: $error');
    return null;
  }
}

Future<bool?> markSpeakerTagPromptsShown(List<String> promptIds) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speaker-tag-prompts/shown',
    headers: {},
    method: 'POST',
    body: jsonEncode(GeneratedSpeakerTagPromptsShownRequest(promptIds: promptIds).toJson()),
  );
  if (response == null || response.statusCode != 200) return null;
  return GeneratedSpeakerTagPromptsShownResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>).firstTime;
}

Future<bool> dismissSpeakerTagPrompts() async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speaker-tag-prompts/dismiss',
    headers: {},
    method: 'POST',
    body: '',
  );
  return response != null && response.statusCode == 204;
}

Future<GeneratedSpeakerTagPromptAnswerResponse?> answerSpeakerTagPrompt(
  GeneratedSpeakerTagPromptAnswerRequest request,
) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speaker-tag-prompts/answer',
    headers: {},
    method: 'POST',
    body: jsonEncode(request.toJson()),
  );
  if (response == null || response.statusCode != 200) {
    Logger.debug('answerSpeakerTagPrompt failed: ${response?.statusCode}');
    return null;
  }
  return GeneratedSpeakerTagPromptAnswerResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

/// WAV bytes for a short window of the user's own stored conversation audio.
Future<Uint8List?> getSpeakerTagPromptClip({
  required String conversationId,
  required double start,
  required double end,
}) async {
  final query = Uri(
    queryParameters: {
      'conversation_id': conversationId,
      'start': start.toStringAsFixed(3),
      'end': end.toStringAsFixed(3),
    },
  ).query;
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speaker-tag-prompts/clip?$query',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200 || response.bodyBytes.isEmpty) return null;
  return response.bodyBytes;
}

Future<GeneratedVoiceProfileSettings?> getVoiceProfileSettings() async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/voice-profile-settings',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200) return null;
  return GeneratedVoiceProfileSettings.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

Future<GeneratedVoiceProfileSettings?> updateVoiceProfileSettings({
  bool? speakerTagPromptsEnabled,
  bool? saveOtherVoiceProfiles,
  required String source,
}) async {
  final body = <String, dynamic>{'source': source};
  if (speakerTagPromptsEnabled != null) body['speaker_tag_prompts_enabled'] = speakerTagPromptsEnabled;
  if (saveOtherVoiceProfiles != null) body['save_other_voice_profiles'] = saveOtherVoiceProfiles;
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/voice-profile-settings',
    headers: {},
    method: 'PATCH',
    body: jsonEncode(body),
  );
  if (response == null || response.statusCode != 200) return null;
  return GeneratedVoiceProfileSettings.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}
