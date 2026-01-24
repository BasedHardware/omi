import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/audio/wav_combiner.dart';
import 'package:omi/utils/logger.dart';

enum AudioDownloadStage {
  preparing,
  downloading,
  processing,
}

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

      final audioFileInfos = await getConversationAudioSignedUrls(conversation.id);

      if (audioFileInfos.isEmpty) {
        Logger.debug('No audio file URLs available');
        return null;
      }

      final cachedFiles = audioFileInfos.where((info) => info.isCached).toList();

      if (cachedFiles.isEmpty) {
        Logger.debug('No cached audio files available');
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

  Future<File> _downloadFile(
    String url,
    String path, {
    void Function(double)? onProgress,
  }) async {
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
