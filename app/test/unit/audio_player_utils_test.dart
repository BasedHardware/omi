import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/audio_player_utils.dart';

void main() {
  late AudioPlayerUtils player;

  setUp(() {
    player = AudioPlayerUtils.instance;
  });

  group('canPlayOrShare', () {
    Wal _makeWal({String? filePath, List<List<int>>? data, WalStorage storage = WalStorage.mem}) {
      return Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 60,
        filePath: filePath,
        data: data ?? const [],
        storage: storage,
      );
    }

    test('returns false when filePath null, data empty, storage mem', () {
      final wal = _makeWal();
      expect(player.canPlayOrShare(wal), isFalse);
    });

    test('returns false when filePath empty string, data empty, storage mem', () {
      final wal = _makeWal(filePath: '');
      expect(player.canPlayOrShare(wal), isFalse);
    });

    test('returns true when filePath is non-empty', () {
      final wal = _makeWal(filePath: '/path/to/audio.wav');
      expect(player.canPlayOrShare(wal), isTrue);
    });

    test('returns true when data is non-empty', () {
      final wal = _makeWal(
        data: [
          [1, 2, 3],
        ],
      );
      expect(player.canPlayOrShare(wal), isTrue);
    });

    test('returns true when storage is sdcard', () {
      final wal = _makeWal(storage: WalStorage.sdcard);
      expect(player.canPlayOrShare(wal), isTrue);
    });

    test('returns true when filePath null but data present', () {
      final wal = _makeWal(
        filePath: null,
        data: [
          [0xFF],
        ],
      );
      expect(player.canPlayOrShare(wal), isTrue);
    });

    test('returns true when all conditions met', () {
      final wal = _makeWal(
        filePath: '/audio.wav',
        data: [
          [1],
        ],
        storage: WalStorage.sdcard,
      );
      expect(player.canPlayOrShare(wal), isTrue);
    });

    test('returns false for disk storage with no file or data', () {
      final wal = _makeWal(storage: WalStorage.disk);
      expect(player.canPlayOrShare(wal), isFalse);
    });
  });

  group('PCM length-prefix binary format parsing (regression for offset bug)', () {
    /// Serialize frames using the same format as _createTempFileFromMemoryData:
    /// [4-byte LE uint32 length][payload bytes] per frame
    Uint8List serializeFrames(List<List<int>> frames) {
      List<int> data = [];
      for (final frame in frames) {
        data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
        final byteFrame = ByteData(frame.length);
        for (int j = 0; j < frame.length; j++) {
          byteFrame.setUint8(j, frame[j]);
        }
        data.addAll(byteFrame.buffer.asUint8List());
      }
      return Uint8List.fromList(data);
    }

    /// Parse frames using the same logic as _convertPcmToWav (after fix):
    /// Read 4-byte LE length from offset, then extract payload
    List<Uint8List> parseFrames(Uint8List fileData) {
      List<Uint8List> frames = [];
      int offset = 0;
      while (offset < fileData.length - 4) {
        final lengthBytes = fileData.sublist(offset, offset + 4);
        final length = ByteData.sublistView(Uint8List.fromList(lengthBytes)).getUint32(0, Endian.little);
        offset += 4;
        if (offset + length > fileData.length) break;
        frames.add(Uint8List.fromList(fileData.sublist(offset, offset + length)));
        offset += length;
      }
      return frames;
    }

    /// Parse using the BUGGY logic (offset+4 instead of offset) to prove it fails
    List<Uint8List> parseFramesBuggy(Uint8List fileData) {
      List<Uint8List> frames = [];
      int offset = 0;
      while (offset < fileData.length - 4) {
        // BUG: reads from offset+4 instead of offset
        if (offset + 8 > fileData.length) break;
        final length = ByteData.sublistView(fileData, offset + 4, offset + 8).getUint32(0, Endian.little);
        offset += 4;
        if (offset + length > fileData.length) break;
        frames.add(Uint8List.fromList(fileData.sublist(offset, offset + length)));
        offset += length;
      }
      return frames;
    }

    test('round-trip: serialize then parse 320-byte PCM16 frames', () {
      // Create 3 frames of 320 bytes each (phone mic PCM16 format)
      final frame1 = List<int>.generate(320, (i) => i & 0xFF);
      final frame2 = List<int>.generate(320, (i) => (i + 100) & 0xFF);
      final frame3 = List<int>.generate(320, (i) => (i + 200) & 0xFF);

      final serialized = serializeFrames([frame1, frame2, frame3]);

      // Verify binary format: 3 * (4 + 320) = 972 bytes
      expect(serialized.length, equals(3 * (4 + 320)));

      // Parse back
      final parsed = parseFrames(serialized);
      expect(parsed.length, equals(3));
      expect(parsed[0], equals(Uint8List.fromList(frame1)));
      expect(parsed[1], equals(Uint8List.fromList(frame2)));
      expect(parsed[2], equals(Uint8List.fromList(frame3)));
    });

    test('buggy parser fails on valid PCM16 frames', () {
      // The buggy version reads payload bytes as length, producing garbage
      final frame = List<int>.generate(320, (i) => i & 0xFF);
      final serialized = serializeFrames([frame]);

      final parsedBuggy = parseFramesBuggy(serialized);
      // Buggy parser reads first 4 payload bytes [0x00, 0x01, 0x02, 0x03]
      // as length = 0x03020100 = 50397440, which exceeds file size → empty result
      expect(parsedBuggy.length, equals(0));

      // Fixed parser works correctly
      final parsedFixed = parseFrames(serialized);
      expect(parsedFixed.length, equals(1));
      expect(parsedFixed[0], equals(Uint8List.fromList(frame)));
    });

    test('adversarial: two frames where buggy parser misaligns', () {
      // With two frames, the buggy parser reads payload bytes as length for
      // the second frame, causing misalignment or failure
      final frame1 = List<int>.generate(320, (i) => 0xAA);
      final frame2 = List<int>.generate(320, (i) => 0xBB);

      final serialized = serializeFrames([frame1, frame2]);
      // Total = 2 * (4 + 320) = 648 bytes

      // Buggy parser frame 1:
      // - reads payload[0:4] = [0xAA, 0xAA, 0xAA, 0xAA] as length = 0xAAAAAAAA = 2863311530
      // - offset becomes 4, 4 + 2863311530 > 648 → breaks → empty result
      final parsedBuggy = parseFramesBuggy(serialized);
      expect(parsedBuggy.length, equals(0));

      // Fixed parser correctly reads both frames
      final parsedFixed = parseFrames(serialized);
      expect(parsedFixed.length, equals(2));
      expect(parsedFixed[0], equals(Uint8List.fromList(frame1)));
      expect(parsedFixed[1], equals(Uint8List.fromList(frame2)));
    });

    test('variable-length frames round-trip correctly', () {
      // Test with non-uniform frame sizes (could happen with flush padding)
      final frames = [
        List<int>.generate(320, (i) => 0xAA),
        List<int>.generate(160, (i) => 0xBB), // Short frame
        List<int>.generate(320, (i) => 0xCC),
      ];

      final serialized = serializeFrames(frames);
      final parsed = parseFrames(serialized);

      expect(parsed.length, equals(3));
      expect(parsed[0].length, equals(320));
      expect(parsed[1].length, equals(160));
      expect(parsed[2].length, equals(320));
      expect(parsed[0].every((b) => b == 0xAA), isTrue);
      expect(parsed[1].every((b) => b == 0xBB), isTrue);
      expect(parsed[2].every((b) => b == 0xCC), isTrue);
    });

    test('single frame round-trip', () {
      final frame = List<int>.generate(320, (i) => 0xFF);
      final serialized = serializeFrames([frame]);
      final parsed = parseFrames(serialized);
      expect(parsed.length, equals(1));
      expect(parsed[0], equals(Uint8List.fromList(frame)));
    });

    test('empty input returns no frames', () {
      final parsed = parseFrames(Uint8List(0));
      expect(parsed.length, equals(0));
    });

    test('truncated length prefix returns no frames', () {
      // Only 3 bytes (less than 4-byte length prefix)
      final parsed = parseFrames(Uint8List.fromList([0x40, 0x01, 0x00]));
      expect(parsed.length, equals(0));
    });
  });
}
