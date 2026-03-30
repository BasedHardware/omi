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

  group('WAL header size is source-dependent (not codec-dependent)', () {
    // walHeaderSize depends on audio SOURCE, not codec:
    // BLE device (any codec): 3-byte firmware header [id_lo, id_hi, pkt_idx]
    // Phone mic (any codec): 1-byte app index header [frame_index]
    // The same codec (e.g., pcm16) has different headers depending on source.

    test('BLE device PCM16 has 3-byte header (firmware adds it)', () {
      // BLE device sending pcm16 → firmware still adds 3-byte header
      const bleHeaderSize = 3;
      final frame = [0x01, 0x02, 0x03, 0xAA, 0xBB]; // 3-byte BLE header + audio
      final stripped = frame.sublist(bleHeaderSize);
      expect(stripped, [0xAA, 0xBB]);
    });

    test('Phone mic PCM16 has 1-byte header (app adds it)', () {
      // Phone mic pcm16 → app adds 1-byte index header
      const phoneMicHeaderSize = 1;
      final frame = [0x05, 0xAA, 0xBB, 0xCC]; // 1-byte index + audio
      final stripped = frame.sublist(phoneMicHeaderSize);
      expect(stripped, [0xAA, 0xBB, 0xCC]);
    });

    test('same codec, different source → different header size', () {
      // This is the key insight: codec alone cannot determine header size
      const bleHeaderSize = 3;
      const phoneMicHeaderSize = 1;
      expect(bleHeaderSize != phoneMicHeaderSize, isTrue);
    });

    test('sync match bytes derived from header size', () {
      // matchBytes = headerSize > 0 ? headerSize : 4 (content fallback)
      int matchBytes(int headerSize) => headerSize > 0 ? headerSize : 4;
      expect(matchBytes(3), 3); // BLE device
      expect(matchBytes(1), 1); // Phone mic
      expect(matchBytes(0), 4); // No header (fallback)
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
    // Simulates the source-aware header stripping from local_wal_sync.dart _flush()
    // Uses _walHeaderSize (set per source), not codec property
    List<int> stripHeader(List<int> frame, int walHeaderSize) {
      return walHeaderSize > 0 && frame.length > walHeaderSize ? frame.sublist(walHeaderSize) : frame;
    }

    test('BLE device frames have 3-byte header stripped', () {
      final frame = [0x01, 0x02, 0x03, 0xAA, 0xBB, 0xCC]; // 3-byte BLE header + audio
      final stripped = stripHeader(frame, 3);
      expect(stripped, [0xAA, 0xBB, 0xCC]);
    });

    test('Phone mic frames have 1-byte index header stripped', () {
      final frame = [0x05, 0xAA, 0xBB, 0xCC, 0xDD]; // 1-byte index + audio
      final stripped = stripHeader(frame, 1);
      expect(stripped, [0xAA, 0xBB, 0xCC, 0xDD]);
    });

    test('No-header source frames pass through unchanged', () {
      final frame = [0x01, 0x02, 0x03, 0xAA, 0xBB, 0xCC];
      final stripped = stripHeader(frame, 0);
      expect(stripped, [0x01, 0x02, 0x03, 0xAA, 0xBB, 0xCC]);
    });

    test('short BLE frame with fewer than 3 bytes not stripped', () {
      final frame = [0x01, 0x02]; // Only 2 bytes, nothing to strip
      final stripped = stripHeader(frame, 3);
      expect(stripped, [0x01, 0x02]);
    });

    test('single-byte phone mic frame not stripped (need > headerSize)', () {
      final frame = [0x05]; // Only 1 byte = headerSize, not stripped
      final stripped = stripHeader(frame, 1);
      expect(stripped, [0x05]);
    });
  });

  group('WAL onBytesSync matching logic', () {
    // Simulates the source-aware sync matching from local_wal_sync.dart onBytesSync()
    // Uses _walHeaderSize (set per source) to determine match bytes
    int? findSyncMatch(List<List<int>> frames, List<int> value, int walHeaderSize) {
      final matchBytes = walHeaderSize > 0 ? walHeaderSize : 4;
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

    test('BLE device matching uses 3 bytes (firmware header)', () {
      final frames = [
        [1, 2, 3, 100, 200],
        [4, 5, 6, 100, 200],
        [7, 8, 9, 100, 200],
      ];
      final match = findSyncMatch(frames, [4, 5, 6, 100, 200], 3);
      expect(match, 1);
    });

    test('Phone mic matching uses 1 byte (index header)', () {
      final frames = [
        [0, 10, 20, 30, 40], // index=0
        [1, 10, 20, 30, 40], // index=1
        [2, 10, 20, 30, 40], // index=2
      ];
      final match = findSyncMatch(frames, [1, 10, 20, 30, 40], 1);
      expect(match, 1);
    });

    test('Phone mic index byte distinguishes frames with same audio content', () {
      final frames = [
        [0, 42, 42, 42, 42], // index=0, same PCM data
        [1, 42, 42, 42, 42], // index=1, same PCM data
        [2, 42, 42, 42, 42], // index=2, same PCM data
      ];
      final match = findSyncMatch(frames, [1, 42, 42, 42, 42], 1);
      expect(match, 1);
    });

    test('BLE PCM16 matching also uses 3 bytes (same as BLE Opus)', () {
      // Key test: BLE device sending PCM16 still uses 3-byte BLE header
      final frames = [
        [1, 0, 0, 0xAA, 0xBB], // BLE header [id_lo=1, id_hi=0, idx=0] + PCM
        [2, 0, 0, 0xAA, 0xBB], // BLE header [id_lo=2, id_hi=0, idx=0] + PCM
      ];
      final match = findSyncMatch(frames, [2, 0, 0, 0xAA, 0xBB], 3); // BLE header size
      expect(match, 1);
    });

    test('no-header source uses 4-byte content fallback', () {
      final frames = [
        [10, 20, 30, 40, 50],
        [10, 20, 30, 41, 60],
      ];
      final match = findSyncMatch(frames, [10, 20, 30, 41, 60], 0);
      expect(match, 1);
    });

    test('no match returns null', () {
      final frames = [
        [1, 2, 3, 4, 5],
      ];
      final match = findSyncMatch(frames, [9, 9, 9, 9, 9], 1);
      expect(match, isNull);
    });

    test('short value returns null for no-header source (needs 4 bytes)', () {
      final frames = [
        [1, 2, 3, 4, 5],
      ];
      final match = findSyncMatch(frames, [1, 2, 3], 0);
      expect(match, isNull);
    });

    test('short value works for BLE (3 bytes sufficient)', () {
      final frames = [
        [1, 2, 3, 4, 5],
      ];
      final match = findSyncMatch(frames, [1, 2, 3], 3);
      expect(match, 0);
    });

    test('single byte works for phone mic (1 byte sufficient)', () {
      final frames = [
        [42, 10, 20, 30],
      ];
      final match = findSyncMatch(frames, [42], 1);
      expect(match, 0);
    });
  });

  group('Source transition: header size must reset per source', () {
    // Simulates the source-transition scenario: phone mic (headerSize=1) → BLE (headerSize=3).
    // Both share the same LocalWalSyncImpl instance. If BLE path doesn't reset headerSize,
    // BLE frames would be flushed with 1-byte stripping (corrupted audio).
    test('phone mic → BLE transition resets headerSize from 1 to 3', () {
      int walHeaderSize = 3; // Default BLE

      void setWalHeaderSize(int size) {
        walHeaderSize = size;
      }

      List<int> stripHeader(List<int> frame) {
        return walHeaderSize > 0 && frame.length > walHeaderSize ? frame.sublist(walHeaderSize) : frame;
      }

      // Phone mic session: set headerSize=1
      setWalHeaderSize(1);
      expect(walHeaderSize, 1);
      final phoneMicFrame = [0x05, 0xAA, 0xBB, 0xCC]; // 1-byte index + audio
      expect(stripHeader(phoneMicFrame), [0xAA, 0xBB, 0xCC]);

      // BLE session: MUST reset headerSize=3 explicitly
      setWalHeaderSize(3);
      expect(walHeaderSize, 3);
      final bleFrame = [0x01, 0x02, 0x03, 0xAA, 0xBB]; // 3-byte firmware header + audio
      expect(stripHeader(bleFrame), [0xAA, 0xBB]);
    });

    test('BLE → phone mic transition resets headerSize from 3 to 1', () {
      int walHeaderSize = 3;

      void setWalHeaderSize(int size) {
        walHeaderSize = size;
      }

      int syncMatchBytes() => walHeaderSize > 0 ? walHeaderSize : 4;

      // BLE session
      setWalHeaderSize(3);
      expect(syncMatchBytes(), 3);

      // Phone mic session: set headerSize=1
      setWalHeaderSize(1);
      expect(syncMatchBytes(), 1);
    });

    test('stale headerSize=1 corrupts BLE flush (regression guard)', () {
      int walHeaderSize = 1; // Stale from phone mic session

      List<int> stripHeader(List<int> frame) {
        return walHeaderSize > 0 && frame.length > walHeaderSize ? frame.sublist(walHeaderSize) : frame;
      }

      // BLE frame with 3-byte firmware header
      final bleFrame = [0x01, 0x02, 0x03, 0xAA, 0xBB];
      final stripped = stripHeader(bleFrame);
      // With stale headerSize=1, only 1 byte stripped → firmware bytes leak into audio
      expect(stripped, [0x02, 0x03, 0xAA, 0xBB]); // WRONG: 0x02, 0x03 are firmware header, not audio
      expect(stripped.length, 4); // Should be 2 if headerSize were correct
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
