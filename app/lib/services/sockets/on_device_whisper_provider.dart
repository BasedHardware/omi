import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:whisper_flutter_new/whisper_flutter_new.dart';

import 'package:omi/models/stt_result.dart';
import 'package:omi/services/experiments/on_device_overflow_gate.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/audio/whisper_pcm.dart';
import 'package:omi/services/sockets/local_stt_failure.dart';
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
        throw const LocalSttFailure('model_missing');
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

  /// Length of the audio in [bytes], in seconds.
  ///
  /// [bytes] is the buffer handed to whisper: a WAV container on every
  /// transcoder path this provider is built with. Deriving the duration from
  /// the whole buffer length divided by a fixed 32000 (16000 Hz * 2 bytes)
  /// counted the 44-byte header as audio and reported an 8 kHz WAV at half
  /// its real length, which corrupts the segment timeline the conversation is
  /// persisted from. Read the sample rate and the PCM length out of the
  /// header instead, and fall back to 16 kHz mono for non-WAV input.
  @visibleForTesting
  static double audioDurationSeconds(Uint8List bytes) {
    const fallbackBytesPerSecond = 32000.0; // 16000 Hz, 16-bit mono
    if (bytes.lengthInBytes < 44) {
      return bytes.lengthInBytes / fallbackBytesPerSecond;
    }

    final data = ByteData.sublistView(bytes);
    final sampleRate = data.getUint32(24, Endian.little);
    final pcmBytes = data.getUint32(40, Endian.little);

    if (sampleRate == 0 || pcmBytes == 0 || pcmBytes > bytes.lengthInBytes - 44) {
      return bytes.lengthInBytes / fallbackBytesPerSecond;
    }

    // 16-bit mono PCM: 2 bytes per sample.
    return pcmBytes / (sampleRate * 2);
  }

  /// Each plugin call allocates and frees a fresh whisper_context. Never pass
  /// more than 30 seconds, including when retained polling audio grows on retry.
  @visibleForTesting
  static Iterable<Uint8List> boundedAudioChunks(Uint8List bytes) sync* {
    if (audioDurationSeconds(bytes) <= 30) {
      yield bytes;
      return;
    }
    final header = ByteData.sublistView(bytes);
    final rate = header.getUint32(24, Endian.little);
    final pcmSize = header.getUint32(40, Endian.little);
    if (rate == 0 ||
        header.getUint16(22, Endian.little) != 1 ||
        header.getUint16(34, Endian.little) != 16 ||
        pcmSize > bytes.length - 44 ||
        pcmSize.isOdd) {
      throw const FormatException('Expected canonical mono 16-bit PCM WAV');
    }
    final limit = 44 + pcmSize;
    final chunkBytes = rate * 2 * 30;
    for (var start = 44; start < limit; start += chunkBytes) {
      final end = (start + chunkBytes).clamp(0, limit);
      yield WavBytes.fromPcm(Uint8List.sublistView(bytes, start, end), sampleRate: rate, numChannels: 1).asBytes();
    }
  }

  @override
  Future<SttTranscriptionResult?> transcribe(
    Uint8List audioData, {
    double audioOffsetSeconds = 0,
    String? language,
  }) async {
    final normalized = WhisperPcm.normalize(audioData);
    final segments = <SttSegment>[];
    final text = <String>[];
    var offset = audioOffsetSeconds;
    for (final chunk in boundedAudioChunks(normalized.wav)) {
      final result = await transcribeChunk(chunk, audioOffsetSeconds: offset, language: language);
      if (result != null) {
        segments.addAll(result.segments);
        if (result.rawText?.isNotEmpty == true) text.add(result.rawText!);
      }
      offset += audioDurationSeconds(chunk);
    }
    return SttTranscriptionResult(
        segments: segments, rawText: text.join(' '), audioEndSeconds: audioOffsetSeconds + normalized.duration);
  }

  @visibleForTesting
  Future<SttTranscriptionResult?> transcribeChunk(
    Uint8List audioData, {
    double audioOffsetSeconds = 0,
    String? language,
  }) async {
    try {
      final enhanced = onDeviceOverflowEnabled ?? await OnDeviceOverflowGate.read();
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
          return null;
        }

        String cleanText = res.text.trim();
        cleanText = cleanText.replaceAll(RegExp(r'\[.*?\]'), '').trim();
        cleanText = cleanText.replaceAll(RegExp(r'\(.*?\)'), '').trim();

        final duration = audioDurationSeconds(audioData);
        final filteredText = _qualityGate.filter(
          cleanText,
          audioData: audioData,
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
      final message = e.toString();
      if (message.contains('OMI_STT_PERMANENT_INPUT:')) throw const LocalSttFailure('invalid_audio');
      if (message.contains('OMI_STT_MODEL_UNAVAILABLE:')) throw const LocalSttFailure('model_invalid');
      rethrow; // Transient decoder failures retain the complete polling buffer.
    }
  }

  @override
  void dispose() {
    _whisper = null;
    _isInitialized = false;
  }
}
