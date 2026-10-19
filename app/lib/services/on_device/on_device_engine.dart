import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

/// Native capability, including language support, wins over OS version alone.
enum OnDeviceEngine { speechAnalyzer, parakeetV2, sfSpeech, whisperTiny }

OnDeviceEngine selectOnDeviceEngine(
    {required bool ios, required int iosMajor, required bool appleLocaleSupported, required bool english}) {
  if (!ios) return OnDeviceEngine.whisperTiny;
  if (iosMajor >= 26 && appleLocaleSupported) return OnDeviceEngine.speechAnalyzer;
  if (iosMajor >= 17 && english) return OnDeviceEngine.parakeetV2;
  return OnDeviceEngine.sfSpeech;
}

class OnDeviceWord {
  const OnDeviceWord(this.text, this.start, this.end);
  final String text;
  final double start;
  final double end;
}

class OnDeviceBatchResult {
  const OnDeviceBatchResult({required this.engine, required this.text, required this.words});
  final String engine;
  final String text;
  final List<OnDeviceWord> words;
}

class AppleBatchEngine {
  static const channel = MethodChannel('com.omi/on_device');
  Future<OnDeviceBatchResult> transcribe(Uint8List wav, {required String language}) async {
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/omi_local_${DateTime.now().microsecondsSinceEpoch}.wav');
    try {
      await file.writeAsBytes(wav, flush: true);
      final result =
          await channel.invokeMapMethod<String, dynamic>('transcribe', {'filePath': file.path, 'language': language});
      if (result == null) throw StateError('Missing native transcription');
      final words = (result['words'] as List? ?? []).map((item) {
        final w = Map<String, dynamic>.from(item as Map);
        return OnDeviceWord(w['text'] as String, (w['start'] as num).toDouble(), (w['end'] as num).toDouble());
      }).toList();
      return OnDeviceBatchResult(engine: result['engine'] as String, text: result['text'] as String, words: words);
    } finally {
      if (await file.exists()) await file.delete();
    }
  }

  Future<bool> canSummarize() async => await channel.invokeMethod<bool>('summaryAvailable') ?? false;
  Future<Map<String, dynamic>> summarize(String text) async {
    final result = await channel.invokeMapMethod<String, dynamic>('summarize', {'text': text});
    if (result == null) throw StateError('Missing native summary');
    return result;
  }

  Future<void> cancel() => channel.invokeMethod<void>('cancel');
}

/// Canonical PCM WAV duration; header bytes are never counted as speech time.
double pcmWavDurationSeconds(Uint8List bytes) {
  if (bytes.length < 44) return bytes.length / 32000.0;
  final data = ByteData.sublistView(bytes);
  final rate = data.getUint32(24, Endian.little);
  final length = data.getUint32(40, Endian.little);
  if (rate == 0 || length == 0 || length > bytes.length - 44) return bytes.length / 32000.0;
  return length / (rate * 2);
}
