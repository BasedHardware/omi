import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:whisper_flutter_new/whisper_flutter_new.dart';

import 'package:omi/models/stt_result.dart';
import 'package:omi/services/experiments/on_device_overflow_gate.dart';
import 'package:omi/services/on_device/on_device_engine.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/services/sockets/on_device_transcript_quality_gate.dart';
import 'package:omi/services/sockets/pure_polling.dart';

class OnDeviceWhisperProvider implements ISttProvider {
  final String modelPath;
  final String language;
  final bool? onDeviceOverflowEnabled;
  Whisper? _whisper;
  bool _isInitialized = false;
  final OnDeviceTranscriptQualityGate _qualityGate = OnDeviceTranscriptQualityGate();

  OnDeviceWhisperProvider({required this.modelPath, this.language = 'en', this.onDeviceOverflowEnabled});

  Future<void> _ensureInitialized() async {
    if (_isInitialized) return;
    try {
      if (!await File(modelPath).exists()) {
        throw Exception('Model file not found at $modelPath');
      }

      final dir = p.dirname(modelPath);
      final filename = p.basename(modelPath);

      WhisperModel targetModel = WhisperModel.tiny;

      if (filename.contains('tiny')) {
        targetModel = WhisperModel.tiny;
      } else if (filename.contains('base')) {
        targetModel = WhisperModel.base;
      } else if (filename.contains('small')) {
        targetModel = WhisperModel.small;
      } else if (filename.contains('medium')) {
        targetModel = WhisperModel.medium;
      } else if (filename.contains('large-v1')) {
        targetModel = WhisperModel.largeV1;
      } else if (filename.contains('large-v2')) {
        targetModel = WhisperModel.largeV2;
      } else {
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

  @visibleForTesting
  TranscribeRequest buildTranscribeRequest(String audioPath, {String? language, bool wordTimestamps = false}) {
    final effectiveLanguage = language ?? this.language;
    return TranscribeRequest(
      audio: audioPath,
      // Empty string lets whisper.cpp auto-detect; used for the 'multi' setting.
      language: effectiveLanguage == 'multi' ? '' : effectiveLanguage,
      isTranslate: false,
      isNoTimestamps: !wordTimestamps,
      splitOnWord: wordTimestamps,
    );
  }

  @override
  Future<SttTranscriptionResult?> transcribe(
    Uint8List audioData, {
    double audioOffsetSeconds = 0,
    String? language,
  }) async {
    try {
      final enhanced = onDeviceOverflowEnabled ?? await OnDeviceOverflowGate.read();
      // Every plugin call creates/frees a fresh whisper_context. Fixed 30s calls
      // therefore reset context; never decode an accumulated long file in one pass.
      if (enhanced && audioData.length > 44 && pcmWavDurationSeconds(audioData) > 30) {
        final rate = ByteData.sublistView(audioData).getUint32(24, Endian.little);
        if (rate <= 0) throw const FormatException('Invalid PCM sample rate');
        final segments = <SttSegment>[];
        var offset = audioOffsetSeconds;
        for (var start = 44; start < audioData.length; start += rate * 2 * 30) {
          final end = (start + rate * 2 * 30).clamp(0, audioData.length);
          final chunk = WavBytes.fromPcm(Uint8List.sublistView(audioData, start, end), sampleRate: rate, numChannels: 1)
              .asBytes();
          final result = await transcribe(chunk, audioOffsetSeconds: offset, language: language);
          if (result != null) segments.addAll(result.segments);
          offset += (end - start) / (rate * 2);
        }
        if (segments.isEmpty) return SttTranscriptionResult(segments: [], rawText: '', audioEndSeconds: offset);
        return SttTranscriptionResult(
            segments: segments, rawText: segments.map((s) => s.text).join(' '), audioEndSeconds: offset);
      }
      final sw = Stopwatch()..start();
      await _ensureInitialized();

      if (_whisper == null) return null;

      final tempDir = await getTemporaryDirectory();
      final tempFile = File('${tempDir.path}/temp_audio_${DateTime.now().millisecondsSinceEpoch}.wav');
      await tempFile.writeAsBytes(audioData);

      try {
        final req = buildTranscribeRequest(tempFile.path, language: language, wordTimestamps: enhanced);

        final res = await _whisper!.transcribe(transcribeRequest: req);

        if (res.text.isEmpty) {
          return enhanced
              ? SttTranscriptionResult(
                  segments: [], rawText: '', audioEndSeconds: audioOffsetSeconds + pcmWavDurationSeconds(audioData))
              : null;
        }

        String cleanText = res.text.trim();
        cleanText = cleanText.replaceAll(RegExp(r'\[.*?\]'), '').trim();
        cleanText = cleanText.replaceAll(RegExp(r'\(.*?\)'), '').trim();

        final duration = pcmWavDurationSeconds(audioData);
        final filteredText = _qualityGate.filter(
          cleanText,
          audioData: audioData,
        );
        if (filteredText == null) {
          CustomSttLogService.instance.warning('OnDeviceWhisper', 'Dropped low-quality local transcript: $cleanText');
          return enhanced
              ? SttTranscriptionResult(segments: [], rawText: '', audioEndSeconds: audioOffsetSeconds + duration)
              : null;
        }

        final speedFactor = sw.elapsedMilliseconds / 1000 / duration;
        CustomSttLogService.instance.info(
          'OnDeviceWhisper',
          'Transcribed ${duration.toStringAsFixed(1)}s in ${sw.elapsedMilliseconds}ms (${speedFactor.toStringAsFixed(2)}x real-time). Text: $filteredText',
        );

        return SttTranscriptionResult(
          audioEndSeconds: enhanced ? audioOffsetSeconds + duration : null,
          segments: enhanced && res.segments?.isNotEmpty == true
              ? [
                  for (final segment in res.segments!)
                    SttSegment(
                        text: segment.text,
                        start: audioOffsetSeconds + segment.fromTs.inMilliseconds / 1000,
                        end: audioOffsetSeconds + segment.toTs.inMilliseconds / 1000,
                        speakerId: 0,
                        sttProvider: 'on_device:whisper_cpp'),
                ]
              : [
                  SttSegment(
                      text: filteredText,
                      start: audioOffsetSeconds,
                      end: audioOffsetSeconds + duration,
                      speakerId: 0,
                      sttProvider: enhanced ? 'on_device:whisper_cpp' : null),
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
      if (onDeviceOverflowEnabled == true || await OnDeviceOverflowGate.read()) rethrow;
      return null;
    }
  }

  @override
  void dispose() {
    _whisper = null;
    _isInitialized = false;
  }
}
