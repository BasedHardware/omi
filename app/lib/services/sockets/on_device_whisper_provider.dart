import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:whisper_flutter_new/whisper_flutter_new.dart';

import 'package:omi/models/stt_result.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/services/sockets/on_device_transcript_quality_gate.dart';
import 'package:omi/services/sockets/pure_polling.dart';

class OnDeviceWhisperProvider implements ISttProvider {
  final String modelPath;
  final String language;
  Whisper? _whisper;
  bool _isInitialized = false;
  final OnDeviceTranscriptQualityGate _qualityGate = OnDeviceTranscriptQualityGate();

  OnDeviceWhisperProvider({required this.modelPath, this.language = 'en'});

  Future<void> _ensureInitialized() async {
    if (_isInitialized) return;
    try {
      if (!await File(modelPath).exists()) {
        throw Exception('Model file not found at $modelPath');
      }

      final dir = p.dirname(modelPath);
      final filename = p.basename(modelPath);

      WhisperModel targetModel = WhisperModel.tiny;

      if (filename.contains('tiny'))
        targetModel = WhisperModel.tiny;
      else if (filename.contains('base'))
        targetModel = WhisperModel.base;
      else if (filename.contains('small'))
        targetModel = WhisperModel.small;
      else if (filename.contains('medium'))
        targetModel = WhisperModel.medium;
      else if (filename.contains('large-v1'))
        targetModel = WhisperModel.largeV1;
      else if (filename.contains('large-v2'))
        targetModel = WhisperModel.largeV2;
      else {
        CustomSttLogService.instance.warning(
          'OnDeviceWhisper',
          'Unknown model filename "$filename", defaulting to tiny.',
        );
      }

      _whisper = Whisper(model: targetModel, modelDir: dir);
      _isInitialized = true;
      CustomSttLogService.instance.info('OnDeviceWhisper', 'Initialized with model: $filename in $dir');
    } catch (e) {
      CustomSttLogService.instance.error('OnDeviceWhisper', 'Initialization error: $e');
      rethrow;
    }
  }

  @override
  Future<SttTranscriptionResult?> transcribe(
    Uint8List audioData, {
    double audioOffsetSeconds = 0,
    String? language,
  }) async {
    try {
      final sw = Stopwatch()..start();
      await _ensureInitialized();

      if (_whisper == null) return null;

      final tempDir = await getTemporaryDirectory();
      final tempFile = File('${tempDir.path}/temp_audio_${DateTime.now().millisecondsSinceEpoch}.wav');
      await tempFile.writeAsBytes(audioData);

      try {
        final req = TranscribeRequest(
          audio: tempFile.path,
          language: (language == 'multi' ? '' : language) ?? '',
          isTranslate: false,
          isNoTimestamps: true,
          splitOnWord: false,
        );

        final res = await _whisper!.transcribe(transcribeRequest: req);

        if (res.text == null || res.text!.isEmpty) {
          return null;
        }

        String cleanText = res.text!.trim();
        cleanText = cleanText.replaceAll(RegExp(r'\[.*?\]'), '').trim();
        cleanText = cleanText.replaceAll(RegExp(r'\(.*?\)'), '').trim();

        // Calculate duration: 16kHz * 2 bytes/sample * 1 channel = 32000 bytes/sec
        final duration = audioData.lengthInBytes / 32000.0;
        final filteredText = _qualityGate.filter(
          cleanText,
          audioData: audioData,
          duration: Duration(microseconds: (duration * Duration.microsecondsPerSecond).round()),
        );
        if (filteredText == null) {
          CustomSttLogService.instance.warning('OnDeviceWhisper', 'Dropped low-quality local transcript: $cleanText');
          return null;
        }

        final speedFactor = sw.elapsedMilliseconds / 1000 / duration;
        CustomSttLogService.instance.info(
          'OnDeviceWhisper',
          'Transcribed ${duration.toStringAsFixed(1)}s in ${sw.elapsedMilliseconds}ms (${speedFactor.toStringAsFixed(2)}x real-time). Text: $filteredText',
        );

        return SttTranscriptionResult(
          segments: [
            SttSegment(text: filteredText, start: audioOffsetSeconds, end: audioOffsetSeconds + duration, speakerId: 0),
          ],
          rawText: filteredText,
        );
      } finally {
        if (await tempFile.exists()) {
          await tempFile.delete();
        }
      }
    } catch (e) {
      CustomSttLogService.instance.error('OnDeviceWhisper', 'Transcription error: $e');
      return null;
    }
  }

  @override
  void dispose() {
    _whisper = null;
    _isInitialized = false;
  }
}
