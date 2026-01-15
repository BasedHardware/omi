import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';

import 'package:path_provider/path_provider.dart';

import 'package:omi/models/stt_result.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/services/sockets/pure_polling.dart';

class OnDeviceAppleProvider implements ISttProvider {
  final String language;
  static const MethodChannel _channel = MethodChannel('com.omi.ios/speech');

  OnDeviceAppleProvider({
    this.language = 'en',
  });

  @override
  Future<SttTranscriptionResult?> transcribe(
    Uint8List audioData, {
    double audioOffsetSeconds = 0,
    String? language,
  }) async {
    try {
      final sw = Stopwatch()..start();

      final tempDir = await getTemporaryDirectory();
      final tempFile = File('${tempDir.path}/temp_apple_audio_${DateTime.now().millisecondsSinceEpoch}.wav');
      await tempFile.writeAsBytes(audioData);

      String effectiveLanguage = language ?? this.language;
      if (effectiveLanguage == 'multi') {
        effectiveLanguage = 'en';
      }

      try {
        final String? result = await _channel.invokeMethod('transcribe', {
          'filePath': tempFile.path,
          'language': effectiveLanguage,
        });

        if (result == null || result.isEmpty) {
          return null;
        }

        // Calculate duration: 16kHz * 2 bytes/sample * 1 channel = 32000 bytes/sec
        final duration = audioData.lengthInBytes / 32000.0;
        CustomSttLogService.instance.info('OnDeviceApple',
            'Transcribed ${duration.toStringAsFixed(1)}s in ${sw.elapsedMilliseconds}ms. Text: $result');

        return SttTranscriptionResult(
          segments: [
            SttSegment(
              text: result,
              start: audioOffsetSeconds,
              end: audioOffsetSeconds + duration,
              speakerId: 0,
            )
          ],
          rawText: result,
        );
      } finally {
        if (await tempFile.exists()) {
          await tempFile.delete();
        }
      }
    } catch (e) {
      CustomSttLogService.instance.error('OnDeviceApple', 'Transcription error: $e');
      return null;
    }
  }

  @override
  void dispose() {
    // Nothing to dispose
  }
}
