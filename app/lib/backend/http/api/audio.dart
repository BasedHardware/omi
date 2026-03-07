import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// Audio file info from signed URL endpoint
class AudioFileUrlInfo {
  final String id;
  final String status; // 'cached' or 'pending'
  final String? signedUrl;
  final double duration;

  AudioFileUrlInfo({
    required this.id,
    required this.status,
    this.signedUrl,
    required this.duration,
  });

  factory AudioFileUrlInfo.fromJson(Map<String, dynamic> json) {
    return AudioFileUrlInfo(
      id: json['id'] ?? '',
      status: json['status'] ?? 'pending',
      signedUrl: json['signed_url'],
      duration: (json['duration'] ?? 0).toDouble(),
    );
  }

  bool get isCached => status == 'cached' && signedUrl != null;
}

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
/// Returns direct GCS URLs when cached, or null for uncached files.
Future<List<AudioFileUrlInfo>> getConversationAudioSignedUrls(String conversationId) async {
  try {
    final headers = await buildHeaders(requireAuthCheck: true);
    final response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sync/audio/$conversationId/urls',
      headers: headers,
      method: 'GET',
      body: '',
    );

    if (response == null || response.statusCode != 200) {
      return [];
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final audioFiles = decoded['audio_files'] as List<dynamic>? ?? [];
    return audioFiles.map((af) => AudioFileUrlInfo.fromJson(af as Map<String, dynamic>)).toList();
  } catch (e) {
    Logger.debug('Error getting audio signed URLs: $e');
    return [];
  }
}

/// List all conversations with audio files for the current user.
Future<List<Map<String, dynamic>>> listUserAudioFiles() async {
  try {
    final headers = await buildHeaders(requireAuthCheck: true);
    final response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sync/audio',
      headers: headers,
      method: 'GET',
      body: '',
    );

    if (response == null || response.statusCode != 200) {
      return [];
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    return (decoded['conversations'] as List<dynamic>?)
            ?.cast<Map<String, dynamic>>() ??
        [];
  } catch (e) {
    Logger.debug('Error listing user audio files: $e');
    return [];
  }
}

/// Delete all private cloud audio files for the current user.
Future<bool> deleteAllUserAudio() async {
  try {
    final headers = await buildHeaders(requireAuthCheck: true);
    final response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sync/audio',
      headers: headers,
      method: 'DELETE',
      body: '',
    );
    return response?.statusCode == 200;
  } catch (e) {
    Logger.debug('Error deleting all user audio: $e');
    return false;
  }
}
