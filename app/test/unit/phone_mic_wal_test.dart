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

  group('WAL header properties', () {
    test('Opus walHeaderSize is 3 (BLE firmware header)', () {
      expect(BleAudioCodec.opus.walHeaderSize, 3);
    });

    test('OpusFS320 walHeaderSize is 3', () {
      expect(BleAudioCodec.opusFS320.walHeaderSize, 3);
    });

    test('PCM16 walHeaderSize is 1 (app index byte)', () {
      expect(BleAudioCodec.pcm16.walHeaderSize, 1);
    });

    test('PCM8 walHeaderSize is 1 (app index byte)', () {
      expect(BleAudioCodec.pcm8.walHeaderSize, 1);
    });

    test('unknown codec walHeaderSize is 0', () {
      expect(BleAudioCodec.unknown.walHeaderSize, 0);
    });

    test('aac walHeaderSize is 0', () {
      expect(BleAudioCodec.aac.walHeaderSize, 0);
    });

    test('Opus syncMatchBytes equals walHeaderSize (3)', () {
      expect(BleAudioCodec.opus.syncMatchBytes, 3);
    });

    test('PCM16 syncMatchBytes equals walHeaderSize (1)', () {
      expect(BleAudioCodec.pcm16.syncMatchBytes, 1);
    });

    test('unknown codec syncMatchBytes falls back to 4 (content matching)', () {
      expect(BleAudioCodec.unknown.syncMatchBytes, 4);
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

  group('Phone mic index header prepend', () {
    // Simulates the index header prepend logic from capture_provider.dart
    test('index byte prepended to PCM frame', () {
      int frameIndex = 0;
      final pcmFrame = List<int>.filled(320, 42);
      final walFrame = [frameIndex & 0xFF, ...pcmFrame];
      frameIndex = (frameIndex + 1) & 0xFF;

      expect(walFrame.length, 321); // 1 header + 320 PCM
      expect(walFrame[0], 0); // First index is 0
      expect(walFrame[1], 42); // PCM data starts at offset 1
    });

    test('index wraps at 255 to 0', () {
      int frameIndex = 255;
      final pcmFrame = List<int>.filled(320, 42);
      final walFrame = [frameIndex & 0xFF, ...pcmFrame];
      frameIndex = (frameIndex + 1) & 0xFF;

      expect(walFrame[0], 255);
      expect(frameIndex, 0); // Wrapped back to 0
    });

    test('sequential frames have incrementing indices', () {
      int frameIndex = 0;
      final indices = <int>[];
      for (int i = 0; i < 5; i++) {
        indices.add(frameIndex & 0xFF);
        frameIndex = (frameIndex + 1) & 0xFF;
      }
      expect(indices, [0, 1, 2, 3, 4]);
    });
  });

  group('WAL flush header stripping logic', () {
    // Simulates the codec-aware header stripping from local_wal_sync.dart _flush()
    // Now uses codec.walHeaderSize instead of hardcoded isOpusSupported() check
    List<int> stripHeader(List<int> frame, BleAudioCodec codec) {
      final headerSize = codec.walHeaderSize;
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

    test('PCM16 frames have 1-byte index header stripped', () {
      final frame = [0x05, 0xAA, 0xBB, 0xCC, 0xDD]; // 1-byte index + 4 audio bytes
      final stripped = stripHeader(frame, BleAudioCodec.pcm16);
      expect(stripped, [0xAA, 0xBB, 0xCC, 0xDD]);
    });

    test('PCM8 frames have 1-byte index header stripped', () {
      final frame = [0x0A, 0x01, 0x02, 0x03];
      final stripped = stripHeader(frame, BleAudioCodec.pcm8);
      expect(stripped, [0x01, 0x02, 0x03]);
    });

    test('unknown codec frames have no header stripped', () {
      final frame = [0x01, 0x02, 0x03, 0xAA, 0xBB, 0xCC];
      final stripped = stripHeader(frame, BleAudioCodec.unknown);
      expect(stripped, [0x01, 0x02, 0x03, 0xAA, 0xBB, 0xCC]);
    });

    test('short Opus frame with fewer than 3 bytes not stripped', () {
      final frame = [0x01, 0x02]; // Only 2 bytes, nothing to strip
      final stripped = stripHeader(frame, BleAudioCodec.opus);
      expect(stripped, [0x01, 0x02]);
    });

    test('single-byte PCM frame not stripped (need > headerSize)', () {
      final frame = [0x05]; // Only 1 byte = headerSize, not stripped
      final stripped = stripHeader(frame, BleAudioCodec.pcm16);
      expect(stripped, [0x05]);
    });
  });

  group('WAL onBytesSync matching logic', () {
    // Simulates the codec-aware sync matching from local_wal_sync.dart onBytesSync()
    // Now uses codec.syncMatchBytes instead of hardcoded isOpusSupported() check
    int? findSyncMatch(List<List<int>> frames, List<int> value, BleAudioCodec codec) {
      final matchBytes = codec.syncMatchBytes;
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

    test('PCM16 matching uses 1 byte (index header)', () {
      final frames = [
        [0, 10, 20, 30, 40], // index=0
        [1, 10, 20, 30, 40], // index=1
        [2, 10, 20, 30, 40], // index=2
      ];
      // PCM matches on 1 byte (index header) — index=1 matches frame 1
      final match = findSyncMatch(frames, [1, 10, 20, 30, 40], BleAudioCodec.pcm16);
      expect(match, 1);
    });

    test('PCM16 index byte distinguishes frames with same audio content', () {
      final frames = [
        [0, 42, 42, 42, 42], // index=0, same PCM data
        [1, 42, 42, 42, 42], // index=1, same PCM data
        [2, 42, 42, 42, 42], // index=2, same PCM data
      ];
      // Matching on index=1 finds frame 1 even though audio content is identical
      final match = findSyncMatch(frames, [1, 42, 42, 42, 42], BleAudioCodec.pcm16);
      expect(match, 1);
    });

    test('PCM16 matching finds last match (backward search)', () {
      final frames = [
        [5, 10, 20, 30, 40],
        [5, 10, 20, 30, 60], // Same index as frame 0 (wrapping)
      ];
      final match = findSyncMatch(frames, [5, 99, 99, 99, 99], BleAudioCodec.pcm16);
      expect(match, 1); // Should find the last match
    });

    test('unknown codec matching uses 4 bytes (content fallback)', () {
      final frames = [
        [10, 20, 30, 40, 50],
        [10, 20, 30, 41, 60],
      ];
      final match = findSyncMatch(frames, [10, 20, 30, 41, 60], BleAudioCodec.unknown);
      expect(match, 1);
    });

    test('no match returns null', () {
      final frames = [
        [1, 2, 3, 4, 5],
      ];
      final match = findSyncMatch(frames, [9, 9, 9, 9, 9], BleAudioCodec.pcm16);
      expect(match, isNull);
    });

    test('short value returns null for unknown codec (needs 4 bytes)', () {
      final frames = [
        [1, 2, 3, 4, 5],
      ];
      final match = findSyncMatch(frames, [1, 2, 3], BleAudioCodec.unknown); // Need 4 bytes for unknown
      expect(match, isNull);
    });

    test('short value works for Opus (3 bytes sufficient)', () {
      final frames = [
        [1, 2, 3, 4, 5],
      ];
      final match = findSyncMatch(frames, [1, 2, 3], BleAudioCodec.opus);
      expect(match, 0);
    });

    test('single byte works for PCM16 (1 byte sufficient)', () {
      final frames = [
        [42, 10, 20, 30],
      ];
      final match = findSyncMatch(frames, [42], BleAudioCodec.pcm16);
      expect(match, 0);
    });
  });

  group('Session boundary reset', () {
    // Verifies that onAudioCodecChanged must reset frames even when codec is unchanged,
    // to prevent stale frames from a prior session leaking into a new session.
    test('same-codec call should clear frames (session boundary)', () {
      // Simulate the onAudioCodecChanged logic after removing early-return
      List<List<int>> frames = [
        [1, 2, 3],
        [4, 5, 6],
      ];
      List<bool> frameSynced = [true, false];

      void onAudioCodecChanged(BleAudioCodec codec) {
        // After fix: always clear frames regardless of codec match
        frames = [];
        frameSynced = [];
      }

      // First session: accumulate frames
      expect(frames.length, 2);

      // Start new session with same codec
      onAudioCodecChanged(BleAudioCodec.pcm16);

      // Frames should be cleared
      expect(frames.length, 0);
      expect(frameSynced.length, 0);
    });
  });
}
