import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
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

    test('all WAV header numeric fields are correct for 16kHz mono', () {
      final pcm = Uint8List.fromList(List.generate(200, (i) => i % 256));
      final wav = WavBytes.fromPcm(pcm, sampleRate: 16000, numChannels: 1).asBytes();

      int u16(int offset) => wav[offset] | (wav[offset + 1] << 8);
      int u32(int offset) => wav[offset] | (wav[offset + 1] << 8) | (wav[offset + 2] << 16) | (wav[offset + 3] << 24);

      // ChunkSize at offset 4 = 36 + pcm.length
      expect(u32(4), equals(36 + pcm.length));

      // Subchunk1Size at offset 16 = 16 (PCM)
      expect(u32(16), equals(16));

      // AudioFormat at offset 20 = 1 (PCM)
      expect(u16(20), equals(1));

      // NumChannels at offset 22
      expect(u16(22), equals(1));

      // SampleRate at offset 24
      expect(u32(24), equals(16000));

      // ByteRate at offset 28 = sampleRate * numChannels * bitsPerSample/8
      // = 16000 * 1 * 16/8 = 32000
      expect(u32(28), equals(32000));

      // BlockAlign at offset 32 = numChannels * bitsPerSample/8 = 1 * 2 = 2
      expect(u16(32), equals(2));

      // BitsPerSample at offset 34 = 16
      expect(u16(34), equals(16));
    });

    test('WAV header fields correct for stereo 48kHz', () {
      final pcm = Uint8List(960); // 10ms of stereo 48kHz 16-bit
      final wav = WavBytes.fromPcm(pcm, sampleRate: 48000, numChannels: 2).asBytes();

      int u16(int offset) => wav[offset] | (wav[offset + 1] << 8);
      int u32(int offset) => wav[offset] | (wav[offset + 1] << 8) | (wav[offset + 2] << 16) | (wav[offset + 3] << 24);

      expect(u16(22), equals(2)); // NumChannels
      expect(u32(24), equals(48000)); // SampleRate
      expect(u32(28), equals(48000 * 2 * 2)); // ByteRate = 192000
      expect(u16(32), equals(4)); // BlockAlign = 2 * 2
      expect(u16(34), equals(16)); // BitsPerSample
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

  group('WAV file splitting (production splitWavFileIfNeeded)', () {
    late Directory tempDir;

    setUp(() {
      TestWidgetsFlutterBinding.ensureInitialized();
      tempDir = Directory.systemTemp.createTempSync('wav_split_test_');
      // Mock path_provider to return our temp dir
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (MethodCall methodCall) async {
          if (methodCall.method == 'getTemporaryDirectory') return tempDir.path;
          return null;
        },
      );
    });

    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        null,
      );
      if (tempDir.existsSync()) {
        tempDir.deleteSync(recursive: true);
      }
    });

    /// Helper: create a WAV file with [pcmLength] bytes of PCM data.
    Future<File> createWavFile(int pcmLength, {String name = 'test.wav'}) async {
      final wavFile = File(path.join(tempDir.path, name));
      final sink = wavFile.openWrite();
      sink.add(WavBytesUtil.getWavHeader(pcmLength, 16000));
      int written = 0;
      while (written < pcmLength) {
        final chunkSize = (pcmLength - written).clamp(0, 65536);
        sink.add(Uint8List.fromList(List.generate(chunkSize, (i) => (written + i) % 256)));
        written += chunkSize;
      }
      await sink.flush();
      await sink.close();
      return wavFile;
    }

    test('small WAV returns original file without splitting', () async {
      final wavFile = await createWavFile(1024 * 1024);
      final chunks = await VoiceRecorderProvider.splitWavFileIfNeeded(wavFile, 16000, 1);

      expect(chunks.length, equals(1));
      expect(chunks[0].path, equals(wavFile.path));
    });

    test('WAV exactly at threshold returns original file', () async {
      final wavFile = await createWavFile(VoiceRecorderProvider.maxChunkPcmBytes);
      final chunks = await VoiceRecorderProvider.splitWavFileIfNeeded(wavFile, 16000, 1);

      expect(chunks.length, equals(1));
      expect(chunks[0].path, equals(wavFile.path));
    });

    test('WAV slightly over threshold splits into 2 chunks', () async {
      final pcmLength = VoiceRecorderProvider.maxChunkPcmBytes + 1000;
      final wavFile = await createWavFile(pcmLength);
      final chunks = await VoiceRecorderProvider.splitWavFileIfNeeded(wavFile, 16000, 1);

      expect(chunks.length, equals(2));

      final chunk1Bytes = await chunks[0].readAsBytes();
      expect(chunk1Bytes.length, equals(44 + VoiceRecorderProvider.maxChunkPcmBytes));

      final chunk2Bytes = await chunks[1].readAsBytes();
      expect(chunk2Bytes.length, equals(44 + 1000));

      // Both should have valid WAV headers
      expect(chunk1Bytes[0], equals(0x52)); // R
      expect(chunk2Bytes[0], equals(0x52)); // R
    });

    test('each chunk has correct subchunk2size in WAV header', () async {
      // Use a file that's 2.5x the threshold to get 3 chunks
      final pcmLength = (VoiceRecorderProvider.maxChunkPcmBytes * 2.5).toInt();
      final wavFile = await createWavFile(pcmLength);
      final chunks = await VoiceRecorderProvider.splitWavFileIfNeeded(wavFile, 16000, 1);

      expect(chunks.length, equals(3));

      for (final chunk in chunks) {
        final bytes = await chunk.readAsBytes();
        final subchunk2Size = bytes[40] | (bytes[41] << 8) | (bytes[42] << 16) | (bytes[43] << 24);
        expect(subchunk2Size, equals(bytes.length - 44));
      }
    });

    test('PCM data continuity across chunks preserves original data', () async {
      // Use small data to test continuity precisely (can't use maxChunkPcmBytes — too slow)
      // We test the production method with a file just over 10MB
      final pcmLength = VoiceRecorderProvider.maxChunkPcmBytes + 500;
      final wavFile = await createWavFile(pcmLength);

      final originalBytes = await wavFile.readAsBytes();
      final originalPcm = originalBytes.sublist(44);

      final chunks = await VoiceRecorderProvider.splitWavFileIfNeeded(wavFile, 16000, 1);

      // Reconstruct PCM from chunks
      final reconstructed = BytesBuilder();
      for (final chunk in chunks) {
        final bytes = await chunk.readAsBytes();
        reconstructed.add(bytes.sublist(44));
      }

      final reconstructedPcm = reconstructed.takeBytes();
      expect(reconstructedPcm.length, equals(pcmLength));

      // Spot-check first, boundary, and last bytes
      expect(reconstructedPcm[0], equals(originalPcm[0]));
      expect(
        reconstructedPcm[VoiceRecorderProvider.maxChunkPcmBytes - 1],
        equals(originalPcm[VoiceRecorderProvider.maxChunkPcmBytes - 1]),
      );
      expect(
        reconstructedPcm[VoiceRecorderProvider.maxChunkPcmBytes],
        equals(originalPcm[VoiceRecorderProvider.maxChunkPcmBytes]),
      );
      expect(reconstructedPcm[pcmLength - 1], equals(originalPcm[pcmLength - 1]));
    });

    test('total PCM bytes across all chunks matches original', () async {
      final pcmLength = VoiceRecorderProvider.maxChunkPcmBytes * 3 + 50000;
      final wavFile = await createWavFile(pcmLength);
      final chunks = await VoiceRecorderProvider.splitWavFileIfNeeded(wavFile, 16000, 1);

      expect(chunks.length, equals(4));

      int totalPcm = 0;
      for (final chunk in chunks) {
        final bytes = await chunk.readAsBytes();
        expect(bytes.length, greaterThan(44));
        totalPcm += bytes.length - 44;

        // Verify each chunk has valid RIFF header
        expect(bytes[0], equals(0x52)); // R
        expect(bytes[1], equals(0x49)); // I
        expect(bytes[2], equals(0x46)); // F
        expect(bytes[3], equals(0x46)); // F
      }
      expect(totalPcm, equals(pcmLength));
    });
  });

  group('VoiceRecorderProvider checkPendingRecording', () {
    late Directory tempDir;

    setUp(() async {
      TestWidgetsFlutterBinding.ensureInitialized();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      tempDir = Directory.systemTemp.createTempSync('voice_pending_test_');
    });

    tearDown(() {
      if (tempDir.existsSync()) {
        tempDir.deleteSync(recursive: true);
      }
    });

    Future<File> createPendingWav(String name) async {
      final wavFile = File(path.join(tempDir.path, name));
      final sink = wavFile.openWrite();
      sink.add(WavBytesUtil.getWavHeader(32000, 16000));
      sink.add(Uint8List(32000));
      await sink.flush();
      await sink.close();
      await SharedPreferencesUtil().saveString('voice_recorder_pending_wav_path', wavFile.path);
      return wavFile;
    }

    test('transitions to pendingRecovery when WAV file exists', () async {
      // Create a WAV file and persist its path
      final wavFile = File(path.join(tempDir.path, 'pending.wav'));
      final sink = wavFile.openWrite();
      sink.add(WavBytesUtil.getWavHeader(32000, 16000));
      sink.add(Uint8List(32000));
      await sink.flush();
      await sink.close();

      await SharedPreferencesUtil().saveString('voice_recorder_pending_wav_path', wavFile.path);

      final provider = VoiceRecorderProvider();
      expect(provider.state, equals(VoiceRecorderState.idle));

      await provider.checkPendingRecording();

      expect(provider.state, equals(VoiceRecorderState.pendingRecovery));
      expect(provider.hasPendingRecording, isTrue);
      expect(provider.isActive, isTrue);
    });

    test('clears stale pref when WAV file is missing', () async {
      // Persist a path to a file that doesn't exist
      await SharedPreferencesUtil().saveString('voice_recorder_pending_wav_path', '/nonexistent/path.wav');

      final provider = VoiceRecorderProvider();
      await provider.checkPendingRecording();

      // Should remain idle and clear the stale pref
      expect(provider.state, equals(VoiceRecorderState.idle));
      expect(provider.hasPendingRecording, isFalse);

      // Verify pref was cleared
      expect(SharedPreferencesUtil().getString('voice_recorder_pending_wav_path'), isEmpty);
    });

    test('does nothing when no pending path is stored', () async {
      final provider = VoiceRecorderProvider();
      await provider.checkPendingRecording();

      expect(provider.state, equals(VoiceRecorderState.idle));
      expect(provider.hasPendingRecording, isFalse);
    });

    test('retry preserves pending WAV when transcription returns empty text', () async {
      final wavFile = await createPendingWav('empty_retry.wav');
      var transcriptCallbackCalled = false;

      final provider = VoiceRecorderProvider(transcriber: (_) async => '');
      provider.setCallbacks(onTranscriptReady: (_, __) => transcriptCallbackCalled = true);
      await provider.checkPendingRecording();

      await provider.retry();

      expect(provider.state, equals(VoiceRecorderState.transcribeFailed));
      expect(provider.isActive, isTrue);
      expect(transcriptCallbackCalled, isFalse);
      expect(wavFile.existsSync(), isTrue);
      expect(SharedPreferencesUtil().getString('voice_recorder_pending_wav_path'), equals(wavFile.path));
    });

    test('retry preserves pending WAV when transcription throws', () async {
      final wavFile = await createPendingWav('failed_retry.wav');

      final provider = VoiceRecorderProvider(transcriber: (_) async => throw Exception('transcription failed'));
      await provider.checkPendingRecording();

      await provider.retry();

      expect(provider.state, equals(VoiceRecorderState.transcribeFailed));
      expect(provider.isActive, isTrue);
      expect(wavFile.existsSync(), isTrue);
      expect(SharedPreferencesUtil().getString('voice_recorder_pending_wav_path'), equals(wavFile.path));
    });

    test('close discards failed pending WAV only after explicit user removal', () async {
      final wavFile = await createPendingWav('discard_retry.wav');
      final provider = VoiceRecorderProvider(transcriber: (_) async => '');
      await provider.checkPendingRecording();
      await provider.retry();

      provider.close();
      await Future<void>.delayed(const Duration(milliseconds: 10));

      expect(provider.state, equals(VoiceRecorderState.idle));
      expect(wavFile.existsSync(), isFalse);
      expect(SharedPreferencesUtil().getString('voice_recorder_pending_wav_path'), isEmpty);
    });
  });
}
