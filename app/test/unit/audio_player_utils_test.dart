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

  group('parseLengthPrefixedFrames (production code, regression for offset bug)', () {
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

    test('round-trip: serialize then parse 320-byte PCM16 frames via production parser', () {
      final frame1 = List<int>.generate(320, (i) => i & 0xFF);
      final frame2 = List<int>.generate(320, (i) => (i + 100) & 0xFF);
      final frame3 = List<int>.generate(320, (i) => (i + 200) & 0xFF);

      final serialized = serializeFrames([frame1, frame2, frame3]);
      expect(serialized.length, equals(3 * (4 + 320)));

      // Uses the PRODUCTION parseLengthPrefixedFrames function
      final parsed = parseLengthPrefixedFrames(serialized);
      expect(parsed.length, equals(3));
      expect(parsed[0], equals(Uint8List.fromList(frame1)));
      expect(parsed[1], equals(Uint8List.fromList(frame2)));
      expect(parsed[2], equals(Uint8List.fromList(frame3)));
    });

    test('production parser handles adversarial payload bytes correctly', () {
      // Two 320-byte frames filled with 0xAA — if offset were wrong,
      // parser would read 0xAAAAAAAA as length and fail
      final frame1 = List<int>.generate(320, (i) => 0xAA);
      final frame2 = List<int>.generate(320, (i) => 0xBB);

      final serialized = serializeFrames([frame1, frame2]);
      final parsed = parseLengthPrefixedFrames(serialized);
      expect(parsed.length, equals(2));
      expect(parsed[0], equals(Uint8List.fromList(frame1)));
      expect(parsed[1], equals(Uint8List.fromList(frame2)));
    });

    test('variable-length frames round-trip via production parser', () {
      final frames = [
        List<int>.generate(320, (i) => 0xAA),
        List<int>.generate(160, (i) => 0xBB),
        List<int>.generate(320, (i) => 0xCC),
      ];

      final serialized = serializeFrames(frames);
      final parsed = parseLengthPrefixedFrames(serialized);

      expect(parsed.length, equals(3));
      expect(parsed[0].length, equals(320));
      expect(parsed[1].length, equals(160));
      expect(parsed[2].length, equals(320));
      expect(parsed[0].every((b) => b == 0xAA), isTrue);
      expect(parsed[1].every((b) => b == 0xBB), isTrue);
      expect(parsed[2].every((b) => b == 0xCC), isTrue);
    });

    test('single frame round-trip via production parser', () {
      final frame = List<int>.generate(320, (i) => 0xFF);
      final serialized = serializeFrames([frame]);
      final parsed = parseLengthPrefixedFrames(serialized);
      expect(parsed.length, equals(1));
      expect(parsed[0], equals(Uint8List.fromList(frame)));
    });

    test('empty input returns no frames', () {
      final parsed = parseLengthPrefixedFrames(Uint8List(0));
      expect(parsed.length, equals(0));
    });

    test('truncated length prefix returns no frames', () {
      final parsed = parseLengthPrefixedFrames(Uint8List.fromList([0x40, 0x01, 0x00]));
      expect(parsed.length, equals(0));
    });

    test('truncated payload returns no frames', () {
      // Length says 320 but only 10 bytes of payload
      final data = Uint8List.fromList([
        ...Uint32List.fromList([320]).buffer.asUint8List(),
        ...List.filled(10, 0xAA),
      ]);
      final parsed = parseLengthPrefixedFrames(data);
      expect(parsed.length, equals(0));
    });
  });
}
