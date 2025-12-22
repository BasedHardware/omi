import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

String getAudioStreamUrl({
  required String conversationId,
  required String audioFileId,
  String format = 'wav',
}) {
  return '${Env.apiBaseUrl}v1/sync/audio/$conversationId/$audioFileId?format=$format';
}

List<String> getConversationAudioUrls({
  required String conversationId,
  required List<String> audioFileIds,
  String format = 'wav',
}) {
  return audioFileIds
      .map((audioFileId) => getAudioStreamUrl(
            conversationId: conversationId,
            audioFileId: audioFileId,
            format: format,
          ))
      .toList();
}

Future<Map<String, String>> getAudioHeaders() async {
  return await buildHeaders(requireAuthCheck: true);
}
