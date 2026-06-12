import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/audio/wav_combiner.dart';
import 'package:omi/utils/logger.dart';

enum AudioDownloadStage { preparing, downloading, processing }

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

      // Asking for URLs also enqueues artifact builds server-side; poll while
      // they finish instead of giving up immediately.
      final deadline = DateTime.now().add(const Duration(seconds: 60));
      var urlsResponse = await getConversationAudioSignedUrls(conversation.id);
      while (urlsResponse.files.isEmpty || urlsResponse.hasPending) {
        if (DateTime.now().isAfter(deadline)) break;
        await Future.delayed(Duration(milliseconds: urlsResponse.pollAfterMs ?? 3000));
        urlsResponse = await getConversationAudioSignedUrls(conversation.id);
      }
      final audioFileInfos = urlsResponse.files;

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

        final filename = 'audio_part_${i + 1}_${DateTime.now().millisecondsSinceEpoch}.${audioInfo.fileExtension}';
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

      final extensions = cachedFiles.map((f) => f.fileExtension).toSet();
      if (extensions.length > 1) {
        // Mixed legacy wav + new mp3 artifacts can't be combined; share the
        // first part rather than producing a corrupt file.
        Logger.debug('Mixed audio artifact formats $extensions, sharing first part only');
        return downloadedFiles.first;
      }

      final extension = extensions.first;
      final combinedFilename = _generateSafeFilename(conversation, extension);
      final combinedPath = '${tempDir.path}/$combinedFilename';

      final File combinedFile;
      if (extension == 'mp3') {
        // MPEG audio frames are self-contained: concatenated MP3 files play
        // as one continuous stream.
        final sink = File(combinedPath).openWrite();
        for (final part in downloadedFiles) {
          await sink.addStream(part.openRead());
        }
        await sink.close();
        combinedFile = File(combinedPath);
      } else {
        combinedFile = await WavCombiner.combineWavFiles(downloadedFiles, combinedPath);
      }
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

  String _generateSafeFilename(ServerConversation conversation, String extension) {
    final now = DateTime.now();
    final timestamp =
        '${now.year}${now.month.toString().padLeft(2, '0')}${now.day.toString().padLeft(2, '0')}_${now.hour.toString().padLeft(2, '0')}${now.minute.toString().padLeft(2, '0')}${now.second.toString().padLeft(2, '0')}';
    return 'omi_$timestamp.$extension';
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
