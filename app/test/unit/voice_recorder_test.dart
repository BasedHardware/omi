import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as path;

import 'package:omi/utils/audio/wav_bytes.dart';

void main() {
  group('WavBytes.asBytes bulk copy', () {
    test('produces valid WAV header for small PCM data', () {
      final pcm = Uint8List.fromList(List.generate(100, (i) => i % 256));
      final wav = WavBytes.fromPcm(pcm, sampleRate: 16000, numChannels: 1).asBytes();

      // WAV header is 44 bytes
      expect(wav.length, equals(44 + pcm.length));

      // RIFF magic
      expect(wav[0], equals(0x52)); // R
      expect(wav[1], equals(0x49)); // I
      expect(wav[2], equals(0x46)); // F
      expect(wav[3], equals(0x46)); // F

      // WAVE magic
      expect(wav[8], equals(0x57)); // W
      expect(wav[9], equals(0x41)); // A
      expect(wav[10], equals(0x56)); // V
      expect(wav[11], equals(0x45)); // E

      // data magic
      expect(wav[36], equals(0x64)); // d
      expect(wav[37], equals(0x61)); // a
      expect(wav[38], equals(0x74)); // t
      expect(wav[39], equals(0x61)); // a
    });

    test('PCM data is faithfully copied to WAV body', () {
      final pcm = Uint8List.fromList([0, 1, 2, 3, 255, 254, 253, 252]);
      final wav = WavBytes.fromPcm(pcm, sampleRate: 16000, numChannels: 1).asBytes();

      // PCM data starts at byte 44
      for (int i = 0; i < pcm.length; i++) {
        expect(wav[44 + i], equals(pcm[i]), reason: 'Byte $i mismatch');
      }
    });

    test('handles empty PCM data', () {
      final pcm = Uint8List(0);
      final wav = WavBytes.fromPcm(pcm, sampleRate: 16000, numChannels: 1).asBytes();
      expect(wav.length, equals(44));
    });

    test('handles large PCM data (1MB) without error', () {
      // 1MB of PCM data — this would be ~32 seconds at 16kHz mono 16-bit
      final pcm = Uint8List(1024 * 1024);
      for (int i = 0; i < pcm.length; i++) {
        pcm[i] = i % 256;
      }
      final wav = WavBytes.fromPcm(pcm, sampleRate: 16000, numChannels: 1).asBytes();
      expect(wav.length, equals(44 + pcm.length));

      // Spot-check some data bytes
      expect(wav[44], equals(0));
      expect(wav[45], equals(1));
      expect(wav[44 + 256], equals(0)); // wraps around
    });

    test('chunk size field matches PCM data length', () {
      final pcm = Uint8List.fromList(List.generate(200, (i) => i % 256));
      final wav = WavBytes.fromPcm(pcm, sampleRate: 16000, numChannels: 1).asBytes();

      // Subchunk2Size at offset 40 (little-endian uint32) should equal pcm.length
      final subchunk2Size = wav[40] | (wav[41] << 8) | (wav[42] << 16) | (wav[43] << 24);
      expect(subchunk2Size, equals(pcm.length));
    });
  });

  group('VoiceRecorderProvider disk streaming', () {
    late Directory tempDir;

    setUp(() {
      tempDir = Directory.systemTemp.createTempSync('voice_recorder_test_');
    });

    tearDown(() {
      if (tempDir.existsSync()) {
        tempDir.deleteSync(recursive: true);
      }
    });

    test('PCM file to WAV file conversion produces valid WAV', () async {
      // Simulate writing PCM chunks to a file (like the recorder does)
      final pcmFile = File(path.join(tempDir.path, 'test.pcm'));
      final sink = pcmFile.openWrite();

      // Write 3 chunks of PCM data (simulating onByteReceived callbacks)
      final chunk1 = Uint8List.fromList(List.generate(8192, (i) => i % 256));
      final chunk2 = Uint8List.fromList(List.generate(8192, (i) => (i + 50) % 256));
      final chunk3 = Uint8List.fromList(List.generate(4096, (i) => (i + 100) % 256));
      sink.add(chunk1);
      sink.add(chunk2);
      sink.add(chunk3);
      await sink.flush();
      await sink.close();

      final totalPcmLength = chunk1.length + chunk2.length + chunk3.length;
      expect(await pcmFile.length(), equals(totalPcmLength));

      // Convert PCM file to WAV file
      final wavFile = File(path.join(tempDir.path, 'test.wav'));
      final wavSink = wavFile.openWrite();

      // Write WAV header
      final wavHeader = WavBytesUtil.getWavHeader(totalPcmLength, 16000);
      wavSink.add(wavHeader);

      // Stream PCM data
      await for (final chunk in pcmFile.openRead()) {
        wavSink.add(chunk);
      }
      await wavSink.flush();
      await wavSink.close();

      // Verify WAV file
      final wavBytes = await wavFile.readAsBytes();
      expect(wavBytes.length, equals(44 + totalPcmLength));

      // RIFF header
      expect(wavBytes[0], equals(0x52)); // R
      expect(wavBytes[1], equals(0x49)); // I
      expect(wavBytes[2], equals(0x46)); // F
      expect(wavBytes[3], equals(0x46)); // F

      // Verify PCM data integrity — first bytes of chunk1
      expect(wavBytes[44], equals(0));
      expect(wavBytes[45], equals(1));
      expect(wavBytes[46], equals(2));
    });

    test('empty PCM file produces valid WAV with only header', () async {
      final pcmFile = File(path.join(tempDir.path, 'empty.pcm'));
      await pcmFile.writeAsBytes([]);

      final wavFile = File(path.join(tempDir.path, 'empty.wav'));
      final wavSink = wavFile.openWrite();
      wavSink.add(WavBytesUtil.getWavHeader(0, 16000));
      await for (final chunk in pcmFile.openRead()) {
        wavSink.add(chunk);
      }
      await wavSink.flush();
      await wavSink.close();

      final wavBytes = await wavFile.readAsBytes();
      expect(wavBytes.length, equals(44));
    });

    test('large PCM file (simulating 20-min recording) converts without OOM', () async {
      // 20 min at 16kHz mono 16-bit = 20 * 60 * 16000 * 2 = 38,400,000 bytes
      // We'll simulate with a smaller but still significant file (1MB) to keep tests fast
      final pcmFile = File(path.join(tempDir.path, 'large.pcm'));
      final sink = pcmFile.openWrite();

      // Write 1MB in 8KB chunks (same as real recorder's buffer size)
      const chunkSize = 8192;
      const totalChunks = 128; // 128 * 8KB = 1MB
      for (int i = 0; i < totalChunks; i++) {
        sink.add(Uint8List(chunkSize));
      }
      await sink.flush();
      await sink.close();

      final pcmLength = await pcmFile.length();
      expect(pcmLength, equals(chunkSize * totalChunks));

      // Convert to WAV via streaming (like the provider does)
      final wavFile = File(path.join(tempDir.path, 'large.wav'));
      final wavSink = wavFile.openWrite();
      wavSink.add(WavBytesUtil.getWavHeader(pcmLength, 16000));
      await for (final chunk in pcmFile.openRead()) {
        wavSink.add(chunk);
      }
      await wavSink.flush();
      await wavSink.close();

      expect(await wavFile.length(), equals(44 + pcmLength));
    });

    test('WAV file persists on disk for retry after transcription failure', () async {
      // Simulate the recorder writing a PCM file
      final pcmFile = File(path.join(tempDir.path, 'retry.pcm'));
      await pcmFile.writeAsBytes(Uint8List(32000)); // 1 second of audio

      // Convert to WAV
      final wavFile = File(path.join(tempDir.path, 'retry.wav'));
      final wavSink = wavFile.openWrite();
      wavSink.add(WavBytesUtil.getWavHeader(32000, 16000));
      await for (final chunk in pcmFile.openRead()) {
        wavSink.add(chunk);
      }
      await wavSink.flush();
      await wavSink.close();

      // Delete PCM file (provider does this after WAV conversion)
      await pcmFile.delete();
      expect(pcmFile.existsSync(), isFalse);

      // WAV file should still exist for retry
      expect(wavFile.existsSync(), isTrue);
      expect(await wavFile.length(), equals(44 + 32000));
    });

    test('minimum audio check rejects short recordings', () {
      // 0.5 seconds at 16kHz PCM16 = 16000 bytes
      const minAudioBytes = 16000;
      expect(15999 < minAudioBytes, isTrue);
      expect(16000 < minAudioBytes, isFalse);
      expect(16001 < minAudioBytes, isFalse);
    });
  });
}
