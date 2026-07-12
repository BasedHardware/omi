import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/audio_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/audio/audio_timeline_mapper.dart';
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
    return AudioFileUrlInfo.fromGenerated(wire.GeneratedAudioFileUrlInfo.fromJson(json));
  }

  factory AudioFileUrlInfo.fromGenerated(wire.GeneratedAudioFileUrlInfo generated) {
    return AudioFileUrlInfo(
      id: generated.id,
      status: generated.status,
      signedUrl: generated.signedUrl,
      contentType: generated.contentType,
      duration: generated.duration,
    );
  }

  bool get isCached => status == 'cached' && signedUrl != null;

  String get fileExtension => contentType == 'audio/mpeg' ? 'mp3' : 'wav';
}

/// Conversation-level dense playback artifact from the /urls endpoint: one MP3
/// with inter-part gaps collapsed, plus the spans manifest for wall-clock
/// mapping (segment seek, scrubber gap shading).
class ConversationAudioUrlInfo {
  final String status; // 'cached' | 'pending' | 'unavailable'
  final String? signedUrl;
  final String? contentType;
  final double? duration; // wall-clock seconds
  final double? capturedDuration; // seconds of actual audio
  final List<ConversationAudioSpan> spans;

  ConversationAudioUrlInfo({
    required this.status,
    this.signedUrl,
    this.contentType,
    this.duration,
    this.capturedDuration,
    this.spans = const [],
  });

  factory ConversationAudioUrlInfo.fromGenerated(wire.GeneratedConversationAudioUrlInfo generated) {
    return ConversationAudioUrlInfo(
      status: generated.status,
      signedUrl: generated.signedUrl,
      contentType: generated.contentType,
      duration: generated.duration,
      capturedDuration: generated.capturedDuration,
      spans: generated.spans
          .map(
            (s) => ConversationAudioSpan(
              fileId: s.fileId,
              wallOffset: s.wallOffset,
              artifactOffset: s.artifactOffset,
              len: s.len,
            ),
          )
          .toList(),
    );
  }

  bool get isCached => status == 'cached' && signedUrl != null;
}

/// Response of the /urls endpoint. While any file is pending the backend is
/// building its playback artifact; poll again after [pollAfterMs].
class AudioUrlsResponse {
  final List<AudioFileUrlInfo> files;
  final ConversationAudioUrlInfo? conversationAudio;
  final int? pollAfterMs;

  AudioUrlsResponse({required this.files, this.conversationAudio, this.pollAfterMs});

  factory AudioUrlsResponse.fromJson(Map<String, dynamic> json) {
    return AudioUrlsResponse.fromGenerated(wire.GeneratedAudioUrlsResponse.fromJson(json));
  }

  factory AudioUrlsResponse.fromGenerated(wire.GeneratedAudioUrlsResponse generated) {
    return AudioUrlsResponse(
      files: generated.audioFiles.map(AudioFileUrlInfo.fromGenerated).toList(),
      conversationAudio: generated.conversationAudio != null
          ? ConversationAudioUrlInfo.fromGenerated(generated.conversationAudio!)
          : null,
      pollAfterMs: generated.pollAfterMs,
    );
  }

  /// 'unavailable' is terminal (source chunks gone) — not worth polling for.
  bool get hasPending => files.any((f) => !f.isCached && f.status != 'unavailable');

  /// Playback can start as soon as EITHER the conversation artifact or the
  /// full per-part set is ready — poll loops exit on this, not [hasPending].
  bool get playbackReady => (conversationAudio?.isCached ?? false) || !hasPending;
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

    final decoded = wire.GeneratedAudioUrlsResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return AudioUrlsResponse.fromGenerated(decoded);
  } catch (e) {
    Logger.debug('Error getting audio signed URLs: $e');
    return AudioUrlsResponse(files: []);
  }
}
