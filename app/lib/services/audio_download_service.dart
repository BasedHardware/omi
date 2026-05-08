import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/audio/wav_combiner.dart';
import 'package:omi/utils/logger.dart';

enum AudioDownloadStage { preparing, downloading, processing }

/// Total wallclock allowed for the merge phase before we give up. Backend
/// stale-job detection kicks in at 25 min; client gives one extra minute of
/// slack to account for poll cadence + network jitter.
const Duration _shareMergeMaxWait = Duration(minutes: 26);

/// Floor and ceiling for the server-suggested poll interval — even if the
/// backend asks for something silly, the client never busy-loops or sleeps so
/// long that progress goes stale.
const Duration _shareMergePollFloor = Duration(seconds: 1);
const Duration _shareMergePollCeiling = Duration(seconds: 10);

class AudioDownloadService {
  final http.Client _client = http.Client();
  final List<File> _tempFiles = [];

  Future<File?> downloadAndCombineAudio(
    ServerConversation conversation, {
    void Function(double)? onProgress,
    void Function(AudioDownloadStage)? onStageChange,
  }) async {
    try {
      if (!conversation.hasAudio()) {
        Logger.debug('Conversation has no audio files');
        return null;
      }

      onStageChange?.call(AudioDownloadStage.preparing);

      // POST /share kicks off (or rejoins) the merge job. For a fully-cached
      // conversation the response is already `completed` with signed URLs.
      AudioShareJob? job = await requestAudioShare(conversation.id);
      if (job == null) {
        Logger.debug('Failed to start audio share job');
        return null;
      }

      // Poll the job until it reaches a terminal state, surfacing server-side
      // merge progress through onProgress so the UI stops showing an
      // indeterminate spinner.
      final mergeDeadline = DateTime.now().add(_shareMergeMaxWait);
      while (!job!.isTerminal) {
        // Bound the poll cadence regardless of what the server suggested.
        // .clamp on int returns num in some Dart positions, so .toInt() avoids
        // an implicit downcast warning when passed to Duration.
        final ms =
            job.pollAfterMs.clamp(_shareMergePollFloor.inMilliseconds, _shareMergePollCeiling.inMilliseconds).toInt();
        await Future.delayed(Duration(milliseconds: ms));

        if (DateTime.now().isAfter(mergeDeadline)) {
          throw Exception('Audio share timed out waiting for merge to complete');
        }
        // Surface "merge progress" inside the preparing stage. The downloader
        // will overwrite onProgress once the cache is ready.
        onProgress?.call(job.progressPct / 100.0);

        if (job.jobId == null) {
          // No job_id but not terminal — should only happen on a malformed
          // server response. Bail rather than tight-loop.
          break;
        }

        final next = await getAudioShareJob(conversation.id, job.jobId!);
        if (next == null) {
          // Transient network failure: keep the previous snapshot and retry.
          continue;
        }
        job = next;
      }

      if (job.status == AudioShareJobStatus.failed) {
        throw Exception('Audio share failed: ${job.error ?? "unknown error"}');
      }

      final cachedFiles = job.audioFiles.where((info) => info.isCached).toList();

      if (cachedFiles.isEmpty) {
        Logger.debug('Audio share completed but no cached files returned');
        return null;
      }

      onStageChange?.call(AudioDownloadStage.downloading);

      final tempDir = await getTemporaryDirectory();
      final downloadedFiles = <File>[];
      var totalProgress = 0.0;

      for (var i = 0; i < cachedFiles.length; i++) {
        final audioInfo = cachedFiles[i];
        if (audioInfo.signedUrl == null) continue;

        final filename = 'audio_part_${i + 1}_${DateTime.now().millisecondsSinceEpoch}.wav';
        final filePath = '${tempDir.path}/$filename';

        final file = await _downloadFile(
          audioInfo.signedUrl!,
          filePath,
          onProgress: (progress) {
            totalProgress = (i + progress) / cachedFiles.length;
            onProgress?.call(totalProgress);
          },
        );

        downloadedFiles.add(file);
        _tempFiles.add(file);
      }

      if (downloadedFiles.isEmpty) {
        Logger.debug('No files were downloaded');
        return null;
      }

      if (downloadedFiles.length == 1) {
        return downloadedFiles.first;
      }

      onStageChange?.call(AudioDownloadStage.processing);

      final combinedFilename = _generateSafeFilename(conversation);
      final combinedPath = '${tempDir.path}/$combinedFilename';
      final combinedFile = await WavCombiner.combineWavFiles(downloadedFiles, combinedPath);
      _tempFiles.add(combinedFile);

      return combinedFile;
    } catch (e) {
      Logger.debug('Error in downloadAndCombineAudio: $e');
      rethrow;
    }
  }

  Future<File> _downloadFile(String url, String path, {void Function(double)? onProgress}) async {
    final request = http.Request('GET', Uri.parse(url));
    final response = await _client.send(request);

    if (response.statusCode != 200) {
      throw Exception('Failed to download file: ${response.statusCode}');
    }

    final contentLength = response.contentLength ?? 0;
    var bytesReceived = 0;

    final file = File(path);
    final sink = file.openWrite();

    try {
      await for (final chunk in response.stream) {
        sink.add(chunk);
        bytesReceived += chunk.length;

        if (contentLength > 0) {
          final progress = bytesReceived / contentLength;
          onProgress?.call(progress);
        }
      }
    } finally {
      await sink.close();
    }

    return file;
  }

  String _generateSafeFilename(ServerConversation conversation) {
    final now = DateTime.now();
    final timestamp =
        '${now.year}${now.month.toString().padLeft(2, '0')}${now.day.toString().padLeft(2, '0')}_${now.hour.toString().padLeft(2, '0')}${now.minute.toString().padLeft(2, '0')}${now.second.toString().padLeft(2, '0')}';
    return 'omi_$timestamp.wav';
  }

  Future<void> cleanup() async {
    for (final file in _tempFiles) {
      try {
        if (await file.exists()) {
          await file.delete();
        }
      } catch (e) {
        Logger.debug('Error deleting temp file: $e');
      }
    }
    _tempFiles.clear();
  }

  void dispose() {
    _client.close();
  }
}
