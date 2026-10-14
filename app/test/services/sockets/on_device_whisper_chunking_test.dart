import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/stt_result.dart';
import 'package:omi/services/sockets/on_device_whisper_provider.dart';
import 'package:omi/utils/audio/wav_bytes.dart';

class RecordingWhisper extends OnDeviceWhisperProvider {
  RecordingWhisper({this.failAt}) : super(modelPath: '/unused');
  final int? failAt;
  final calls = <double>[];
  @override
  Future<SttTranscriptionResult?> transcribeChunk(
    Uint8List data, {
    double audioOffsetSeconds = 0,
    String? language,
  }) async {
    if (calls.length == failAt) throw StateError('decoder failed');
    final duration = OnDeviceWhisperProvider.audioDurationSeconds(data);
    calls.add(duration);
    expect(language, 'de');
    return SttTranscriptionResult(rawText: 'chunk', segments: [
      SttSegment(text: 'chunk', start: audioOffsetSeconds, end: audioOffsetSeconds + duration),
    ]);
  }
}

void main() {
  for (final rate in [8000, 16000]) {
    test('65 seconds at $rate Hz decode as 30/30/5 with exact offsets and custody', () async {
      final pcm = Uint8List(rate * 2 * 65);
      for (var i = 0; i < pcm.length; i++) {
        pcm[i] = i % 251;
      }
      final wav = WavBytes.fromPcm(pcm, sampleRate: rate, numChannels: 1).asBytes();
      final parts = OnDeviceWhisperProvider.boundedAudioChunks(wav).toList();
      final restored = BytesBuilder();
      for (final part in parts) {
        restored.add(part.sublist(44));
      }
      expect(restored.toBytes(), pcm);
      final provider = RecordingWhisper();
      final result = await provider.transcribe(wav, language: 'de', audioOffsetSeconds: 10);
      expect(provider.calls, [30, 30, 5]);
      expect(result!.segments.map((s) => s.start), [10, 40, 70]);
      expect(result.segments.last.end, 75);
    });
  }
  test('failed middle chunk propagates for whole-buffer retry', () async {
    final wav = WavBytes.fromPcm(Uint8List(16000 * 2 * 65), sampleRate: 16000, numChannels: 1).asBytes();
    await expectLater(RecordingWhisper(failAt: 1).transcribe(wav, language: 'de'), throwsStateError);
  });
  test('short recordings stay one call', () async {
    final provider = RecordingWhisper();
    final wav = WavBytes.fromPcm(Uint8List(32000 * 5), sampleRate: 16000, numChannels: 1).asBytes();
    await provider.transcribe(wav, language: 'de');
    expect(provider.calls, [5]);
  });
}
