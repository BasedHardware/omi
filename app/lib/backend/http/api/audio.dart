import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// Audio file info from signed URL endpoint
class AudioFileUrlInfo {
  final String id;
  final String status; // 'cached' | 'pending' | 'unavailable'
  final String? signedUrl;
  final String? contentType;
  final double duration;

  AudioFileUrlInfo({required this.id, required this.status, this.signedUrl, this.contentType, required this.duration});

  factory AudioFileUrlInfo.fromJson(Map<String, dynamic> json) {
    return AudioFileUrlInfo(
      id: json['id'] ?? '',
      status: json['status'] ?? 'pending',
      signedUrl: json['signed_url'],
      contentType: json['content_type'],
      duration: (json['duration'] ?? 0).toDouble(),
    );
  }

  bool get isCached => status == 'cached' && signedUrl != null;

  String get fileExtension => contentType == 'audio/mpeg' ? 'mp3' : 'wav';
}

/// Response of the /urls endpoint. While any file is pending the backend is
/// building its playback artifact; poll again after [pollAfterMs].
class AudioUrlsResponse {
  final List<AudioFileUrlInfo> files;
  final int? pollAfterMs;

  AudioUrlsResponse({required this.files, this.pollAfterMs});

  /// 'unavailable' is terminal (source chunks gone) — not worth polling for.
  bool get hasPending => files.any((f) => !f.isCached && f.status != 'unavailable');
}

String getAudioStreamUrl({required String conversationId, required String audioFileId, String format = 'wav'}) {
  return '${Env.apiBaseUrl}v1/sync/audio/$conversationId/$audioFileId?format=$format';
}

List<String> getConversationAudioUrls({
  required String conversationId,
  required List<String> audioFileIds,
  String format = 'wav',
}) {
  return audioFileIds
      .map((audioFileId) => getAudioStreamUrl(conversationId: conversationId, audioFileId: audioFileId, format: format))
      .toList();
}

Future<Map<String, String>> getAudioHeaders() async {
  return await buildHeaders(requireAuthCheck: true);
}

/// Pre-cache audio files for a conversation.
Future<void> precacheConversationAudio(String conversationId) async {
  try {
    final headers = await buildHeaders(requireAuthCheck: true);
    await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sync/audio/$conversationId/precache',
      headers: headers,
      method: 'POST',
      body: '',
    );
  } catch (e) {
    Logger.debug('Error pre-caching audio: $e');
  }
}

/// Get signed URLs for audio files in a conversation.
/// Returns direct GCS URLs when cached; pending files are being built
/// server-side and should be re-polled after [AudioUrlsResponse.pollAfterMs].
Future<AudioUrlsResponse> getConversationAudioSignedUrls(String conversationId) async {
  try {
    final headers = await buildHeaders(requireAuthCheck: true);
    final response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sync/audio/$conversationId/urls',
      headers: headers,
      method: 'GET',
      body: '',
    );

    if (response == null || response.statusCode != 200) {
      return AudioUrlsResponse(files: []);
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final audioFiles = decoded['audio_files'] as List<dynamic>? ?? [];
    return AudioUrlsResponse(
      files: audioFiles.map((af) => AudioFileUrlInfo.fromJson(af as Map<String, dynamic>)).toList(),
      pollAfterMs: decoded['poll_after_ms'],
    );
  } catch (e) {
    Logger.debug('Error getting audio signed URLs: $e');
    return AudioUrlsResponse(files: []);
  }
}
