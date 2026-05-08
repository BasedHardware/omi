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

  AudioFileUrlInfo({required this.id, required this.status, this.signedUrl, required this.duration});

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

/// Status of an async audio-share job. Mirrors the backend status field
/// (queued | processing | completed | failed). Synthetic shortcut: when
/// every audio file is already cached, the backend skips the job entirely
/// and returns `completed` directly.
enum AudioShareJobStatus { queued, processing, completed, failed }

AudioShareJobStatus _parseShareStatus(String? raw) {
  switch (raw) {
    case 'queued':
      return AudioShareJobStatus.queued;
    case 'processing':
      return AudioShareJobStatus.processing;
    case 'completed':
      return AudioShareJobStatus.completed;
    case 'failed':
      return AudioShareJobStatus.failed;
    default:
      return AudioShareJobStatus.queued;
  }
}

/// One snapshot of an audio-share job. Returned by both the POST /share
/// kickoff and each GET /share/{job_id} poll.
class AudioShareJob {
  /// `null` only when the backend short-circuited on a fully-cached conversation.
  final String? jobId;
  final AudioShareJobStatus status;
  final double progressPct;
  final List<AudioFileUrlInfo> audioFiles;
  final String? error;
  final int pollAfterMs;

  AudioShareJob({
    required this.jobId,
    required this.status,
    required this.progressPct,
    required this.audioFiles,
    this.error,
    required this.pollAfterMs,
  });

  factory AudioShareJob.fromJson(Map<String, dynamic> json) {
    final files = (json['audio_files'] as List<dynamic>? ?? [])
        .map((af) => AudioFileUrlInfo.fromJson(af as Map<String, dynamic>))
        .toList();
    return AudioShareJob(
      jobId: json['job_id'] as String?,
      status: _parseShareStatus(json['status'] as String?),
      progressPct: (json['progress_pct'] ?? 0).toDouble(),
      audioFiles: files,
      error: json['error'] as String?,
      pollAfterMs: (json['poll_after_ms'] ?? 3000) as int,
    );
  }

  bool get isTerminal => status == AudioShareJobStatus.completed || status == AudioShareJobStatus.failed;
}

/// Kick off (or rejoin) an async share-audio merge. Returns immediately:
/// either `completed` (cache hit, signed URLs populated) or `queued/processing`
/// with a job_id to poll via [getAudioShareJob].
Future<AudioShareJob?> requestAudioShare(String conversationId) async {
  try {
    final headers = await buildHeaders(requireAuthCheck: true);
    final response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sync/audio/$conversationId/share',
      headers: headers,
      method: 'POST',
      body: '',
    );

    if (response == null) {
      return null;
    }
    // 200 (cache hit, completed) and 202 (job started/rejoined) both have a body
    if (response.statusCode != 200 && response.statusCode != 202) {
      Logger.debug('requestAudioShare: unexpected status ${response.statusCode}');
      return null;
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    return AudioShareJob.fromJson(decoded);
  } catch (e) {
    Logger.debug('Error requesting audio share: $e');
    return null;
  }
}

/// Poll an audio-share job by id. Returns `null` only on transport failure;
/// terminal failures (404, expired, error) come back as a populated [AudioShareJob]
/// with `status == failed`.
Future<AudioShareJob?> getAudioShareJob(String conversationId, String jobId) async {
  try {
    final headers = await buildHeaders(requireAuthCheck: true);
    final response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sync/audio/$conversationId/share/$jobId',
      headers: headers,
      method: 'GET',
      body: '',
    );

    if (response == null) {
      return null;
    }
    if (response.statusCode == 404) {
      return AudioShareJob(
        jobId: jobId,
        status: AudioShareJobStatus.failed,
        progressPct: 0.0,
        audioFiles: const [],
        error: 'Job not found or expired',
        pollAfterMs: 0,
      );
    }
    if (response.statusCode != 200) {
      Logger.debug('getAudioShareJob: unexpected status ${response.statusCode}');
      return null;
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    return AudioShareJob.fromJson(decoded);
  } catch (e) {
    Logger.debug('Error polling audio share job: $e');
    return null;
  }
}
