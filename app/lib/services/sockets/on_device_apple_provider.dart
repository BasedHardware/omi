import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart' show MethodChannel, PlatformException;

import 'package:path_provider/path_provider.dart';

import 'package:omi/models/stt_result.dart';
import 'package:omi/services/experiments/on_device_overflow_gate.dart';
import 'package:omi/services/on_device/on_device_engine.dart';
import 'package:omi/utils/audio/whisper_pcm.dart';
import 'package:omi/services/sockets/apple_speech_readiness.dart';
import 'package:omi/services/sockets/local_stt_failure.dart';
import 'package:omi/services/experiments/apple_speech_analyzer_gate.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/services/sockets/on_device_transcript_quality_gate.dart';
import 'package:omi/services/sockets/pure_polling.dart';

class OnDeviceAppleProvider implements ISttProvider, RecoverableLocalSttProvider {
  final String language;
  final Future<bool> Function()? useSpeechAnalyzer;
  static const MethodChannel _channel = MethodChannel('com.omi.ios/speech');
  final OnDeviceTranscriptQualityGate _qualityGate = OnDeviceTranscriptQualityGate();

  OnDeviceAppleProvider({this.language = 'en', this.useSpeechAnalyzer});

  /// Whether iOS has an on-device recognizer (language model installed, not
  /// network-backed) for [language]. Bare codes like "en" are resolved
  /// natively to an installed full locale such as en-US. Returns false on any
  /// channel error so callers treat "unknown" as "unavailable".
  static Future<bool> isOnDeviceAvailable(String language,
      {Future<bool> Function()? useSpeechAnalyzer, bool? isIOS}) async {
    if (!(isIOS ?? Platform.isIOS)) return false;
    try {
      if (useSpeechAnalyzer == null && await OnDeviceOverflowGate.read()) return (await readiness(language)).ready;
      final available = await _channel.invokeMethod<bool>('onDeviceAvailable', {
        'language': language,
        'useSpeechAnalyzer': await (useSpeechAnalyzer ?? AppleSpeechAnalyzerGate.useNewEngine)()
      });
      return available ?? false;
    } catch (e) {
      CustomSttLogService.instance.error('OnDeviceApple', 'Availability check failed: $e');
      return false;
    }
  }

  static Future<AppleSpeechReadiness> readiness(
    String language, {
    Future<bool> Function()? useSpeechAnalyzer,
    bool prepare = false,
  }) async {
    try {
      var overflowUsesLegacy = false;
      if (useSpeechAnalyzer == null && await OnDeviceOverflowGate.read()) {
        final batch = await AppleBatchEngine.channel.invokeMapMethod<String, dynamic>('status', {'language': language});
        final engine = batch?['engine'] as String? ?? 'unavailable';
        overflowUsesLegacy = engine == 'sfspeech';
        if (!overflowUsesLegacy) {
          return AppleSpeechReadiness(engine, batch?['phase'] == 'installed' ? 'ready' : 'unavailable');
        }
      }
      final data = await _channel.invokeMapMethod<String, dynamic>(prepare ? 'prepareSpeech' : 'readiness', {
        'language': language,
        'useSpeechAnalyzer': !overflowUsesLegacy && await (useSpeechAnalyzer ?? AppleSpeechAnalyzerGate.useNewEngine)(),
      });
      return AppleSpeechReadiness.fromMap(data);
    } catch (_) {
      return const AppleSpeechReadiness('unknown', 'unavailable');
    }
  }

  @override
  Future<bool> isReadyToRetry() async => (await readiness(language, useSpeechAnalyzer: useSpeechAnalyzer)).ready;

  @override
  Future<SttTranscriptionResult?> transcribe(
    Uint8List audioData, {
    double audioOffsetSeconds = 0,
    String? language,
  }) async {
    try {
      final normalized = WhisperPcm.normalize(audioData);
      if (await OnDeviceOverflowGate.read()) {
        final result = await AppleBatchEngine().transcribe(normalized.wav, language: language ?? this.language);
        final duration = normalized.duration;
        if (result.text.trim().isEmpty) {
          return SttTranscriptionResult(segments: [], rawText: '', audioEndSeconds: audioOffsetSeconds + duration);
        }
        return SttTranscriptionResult(rawText: result.text, audioEndSeconds: audioOffsetSeconds + duration, segments: [
          if (result.words.isEmpty)
            SttSegment(
                text: result.text,
                start: audioOffsetSeconds,
                end: audioOffsetSeconds + duration,
                speakerId: 0,
                sttProvider: 'on_device:${result.engine}')
          else
            for (final word in result.words)
              SttSegment(
                  text: word.text,
                  start: audioOffsetSeconds + word.start,
                  end: audioOffsetSeconds + word.end,
                  speakerId: 0,
                  sttProvider: 'on_device:${result.engine}'),
        ]);
      }
      final sw = Stopwatch()..start();

      final tempDir = await getTemporaryDirectory();
      final tempFile = File('${tempDir.path}/temp_apple_audio_${DateTime.now().millisecondsSinceEpoch}.wav');
      await tempFile.writeAsBytes(normalized.wav);

      String effectiveLanguage = language ?? this.language;
      if (effectiveLanguage == 'multi') {
        effectiveLanguage = 'en';
      }

      try {
        final String? result = await _channel.invokeMethod('transcribe', {
          'filePath': tempFile.path,
          'language': effectiveLanguage,
          'useSpeechAnalyzer': await (useSpeechAnalyzer ?? AppleSpeechAnalyzerGate.useNewEngine)(),
        });

        if (result == null || result.isEmpty) {
          return SttTranscriptionResult(audioEndSeconds: audioOffsetSeconds + normalized.duration);
        }

        final duration = normalized.duration;
        final filteredText = _qualityGate.filter(
          result,
          audioData: audioData,
        );
        if (filteredText == null) {
          CustomSttLogService.instance.warning('OnDeviceApple', 'Dropped low-quality local transcript: $result');
          return SttTranscriptionResult(audioEndSeconds: audioOffsetSeconds + duration);
        }

        CustomSttLogService.instance.info(
          'OnDeviceApple',
          'Transcribed ${duration.toStringAsFixed(1)}s in ${sw.elapsedMilliseconds}ms. Text: $filteredText',
        );

        return SttTranscriptionResult(
          audioEndSeconds: audioOffsetSeconds + duration,
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
      // Keep the native domain/code before translating setup failures for the
      // recovery UI. Polling otherwise only sees the bounded LocalSttFailure.
      CustomSttLogService.instance.error('OnDeviceApple', 'Transcription error: $e');
      if (e is PlatformException && useSpeechAnalyzer == null && await OnDeviceOverflowGate.read()) {
        final state = await readiness(language ?? this.language);
        if (!state.ready) throw LocalSttFailure(state.status, canProbeRecovery: true);
      }
      if (e is PlatformException && ['UNAUTHORIZED', 'UNAVAILABLE', 'INVALID_ARGS'].contains(e.code)) {
        final details = e.details;
        final status = details is Map ? details['status'] as String? : null;
        throw LocalSttFailure(status ?? e.code.toLowerCase(), canProbeRecovery: e.code != 'INVALID_ARGS');
      }
      rethrow; // Keep failed/timed-out audio in the polling buffer for retry.
    }
  }

  @override
  void dispose() {
    // Nothing to dispose
  }
}
