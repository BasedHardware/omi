import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';

void main() {
  group('Wal PCM codec support', () {
    test('PCM16 WAL filename contains pcm16 codec', () {
      final wal = Wal(
        timerStart: 1710000000,
        codec: BleAudioCodec.pcm16,
        seconds: 60,
        device: 'phone-mic',
      );
      final filename = wal.getFileName();
      expect(filename, contains('pcm16'));
      expect(filename, contains('phonemic')); // device name sanitized: hyphens removed
      expect(filename, contains('16000'));
      expect(filename, endsWith('.bin'));
    });

    test('PCM8 WAL filename contains pcm8 codec', () {
      final wal = Wal(
        timerStart: 1710000000,
        codec: BleAudioCodec.pcm8,
        seconds: 60,
        device: 'phone-mic',
      );
      final filename = wal.getFileName();
      expect(filename, contains('pcm8'));
    });

    test('Opus WAL filename contains opus codec', () {
      final wal = Wal(
        timerStart: 1710000000,
        codec: BleAudioCodec.opus,
        seconds: 60,
        device: 'omi',
      );
      final filename = wal.getFileName();
      expect(filename, contains('opus'));
    });

    test('PCM16 codec reports non-Opus', () {
      expect(BleAudioCodec.pcm16.isOpusSupported(), isFalse);
    });

    test('PCM8 codec reports non-Opus', () {
      expect(BleAudioCodec.pcm8.isOpusSupported(), isFalse);
    });

    test('Opus codec reports Opus-supported', () {
      expect(BleAudioCodec.opus.isOpusSupported(), isTrue);
    });

    test('OpusFS320 codec reports Opus-supported', () {
      expect(BleAudioCodec.opusFS320.isOpusSupported(), isTrue);
    });

    test('PCM16 frames per second is 100', () {
      expect(BleAudioCodec.pcm16.getFramesPerSecond(), 100);
    });
  });

  group('Phone mic WAL frame splitting', () {
    // Simulates the frame splitting logic from capture_provider.dart streamRecording()
    List<List<int>> splitIntoFrames(List<int> rawBytes, int frameSize) {
      final frames = <List<int>>[];
      final buffer = List<int>.from(rawBytes);
      while (buffer.length >= frameSize) {
        frames.add(buffer.sublist(0, frameSize));
        buffer.removeRange(0, frameSize);
      }
      return frames;
    }

    test('splits exact multiple into correct frames', () {
      // 640 bytes = 2 frames of 320
      final raw = List<int>.filled(640, 42);
      final frames = splitIntoFrames(raw, 320);
      expect(frames.length, 2);
      expect(frames[0].length, 320);
      expect(frames[1].length, 320);
    });

    test('partial remainder stays in buffer', () {
      // 500 bytes = 1 frame + 180 remaining
      final raw = List<int>.filled(500, 42);
      final buffer = List<int>.from(raw);
      final frames = <List<int>>[];
      while (buffer.length >= 320) {
        frames.add(buffer.sublist(0, 320));
        buffer.removeRange(0, 320);
      }
      expect(frames.length, 1);
      expect(buffer.length, 180);
    });

    test('empty input produces no frames', () {
      final frames = splitIntoFrames([], 320);
      expect(frames.length, 0);
    });

    test('sub-frame input produces no frames', () {
      final raw = List<int>.filled(100, 42);
      final frames = splitIntoFrames(raw, 320);
      expect(frames.length, 0);
    });

    test('large buffer splits correctly', () {
      // 3200 bytes = 10 frames of 320
      final raw = List<int>.filled(3200, 42);
      final frames = splitIntoFrames(raw, 320);
      expect(frames.length, 10);
    });
  });

  group('WAL flush header stripping logic', () {
    // Simulates the codec-aware header stripping from local_wal_sync.dart _flush()
    List<int> stripHeader(List<int> frame, BleAudioCodec codec) {
      final headerSize = codec.isOpusSupported() ? 3 : 0;
      return headerSize > 0 && frame.length > headerSize ? frame.sublist(headerSize) : frame;
    }

    test('Opus frames have 3-byte header stripped', () {
      final frame = [0x01, 0x02, 0x03, 0xAA, 0xBB, 0xCC]; // 3-byte header + 3 audio bytes
      final stripped = stripHeader(frame, BleAudioCodec.opus);
      expect(stripped, [0xAA, 0xBB, 0xCC]);
    });

    test('OpusFS320 frames have 3-byte header stripped', () {
      final frame = [0x01, 0x02, 0x03, 0xAA, 0xBB];
      final stripped = stripHeader(frame, BleAudioCodec.opusFS320);
      expect(stripped, [0xAA, 0xBB]);
    });

    test('PCM16 frames have no header stripped', () {
      final frame = [0x01, 0x02, 0x03, 0xAA, 0xBB, 0xCC];
      final stripped = stripHeader(frame, BleAudioCodec.pcm16);
      expect(stripped, [0x01, 0x02, 0x03, 0xAA, 0xBB, 0xCC]);
    });

    test('PCM8 frames have no header stripped', () {
      final frame = [0x01, 0x02, 0x03];
      final stripped = stripHeader(frame, BleAudioCodec.pcm8);
      expect(stripped, [0x01, 0x02, 0x03]);
    });

    test('short Opus frame with fewer than 3 bytes not stripped', () {
      final frame = [0x01, 0x02]; // Only 2 bytes, nothing to strip
      final stripped = stripHeader(frame, BleAudioCodec.opus);
      expect(stripped, [0x01, 0x02]);
    });
  });

  group('WAL onBytesSync matching logic', () {
    // Simulates the codec-aware sync matching from local_wal_sync.dart onBytesSync()
    int? findSyncMatch(List<List<int>> frames, List<int> value, BleAudioCodec codec) {
      final matchBytes = codec.isOpusSupported() ? 3 : 4;
      if (value.length < matchBytes) return null;
      for (int i = frames.length - 1; i >= 0; i--) {
        if (frames[i].length < matchBytes) continue;
        bool match = true;
        for (int j = 0; j < matchBytes; j++) {
          if (frames[i][j] != value[j]) {
            match = false;
            break;
          }
        }
        if (match) return i;
      }
      return null;
    }

    test('Opus matching uses 3 bytes (BLE header)', () {
      final frames = [
        [1, 2, 3, 100, 200],
        [4, 5, 6, 100, 200],
        [7, 8, 9, 100, 200],
      ];
      final match = findSyncMatch(frames, [4, 5, 6, 100, 200], BleAudioCodec.opus);
      expect(match, 1);
    });

    test('PCM16 matching uses 4 bytes (audio content)', () {
      final frames = [
        [10, 20, 30, 40, 50],
        [10, 20, 30, 41, 60],
        [10, 20, 30, 42, 70],
      ];
      // PCM matches on 4 bytes — [10,20,30,41] matches frame 1
      final match = findSyncMatch(frames, [10, 20, 30, 41, 60], BleAudioCodec.pcm16);
      expect(match, 1);
    });

    test('PCM16 matching finds last match (backward search)', () {
      final frames = [
        [10, 20, 30, 40, 50],
        [10, 20, 30, 40, 60], // Same first 4 bytes as frame 0
      ];
      final match = findSyncMatch(frames, [10, 20, 30, 40, 99], BleAudioCodec.pcm16);
      expect(match, 1); // Should find the last match
    });

    test('no match returns null', () {
      final frames = [
        [1, 2, 3, 4, 5],
      ];
      final match = findSyncMatch(frames, [9, 9, 9, 9, 9], BleAudioCodec.pcm16);
      expect(match, isNull);
    });

    test('short value returns null for PCM', () {
      final frames = [
        [1, 2, 3, 4, 5],
      ];
      final match = findSyncMatch(frames, [1, 2, 3], BleAudioCodec.pcm16); // Need 4 bytes for PCM
      expect(match, isNull);
    });

    test('short value works for Opus (3 bytes sufficient)', () {
      final frames = [
        [1, 2, 3, 4, 5],
      ];
      final match = findSyncMatch(frames, [1, 2, 3], BleAudioCodec.opus);
      expect(match, 0);
    });
  });
}
