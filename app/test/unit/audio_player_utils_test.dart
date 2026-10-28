import 'dart:async';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:flutter/services.dart';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/audio_player_utils.dart';
import 'package:omi/utils/audio/wal_wav_worker.dart' show readLengthPrefixedFrames;

Int16List _decodeTestOpusFrame(Uint8List frame, int sampleRate, int channels) {
  // A synthetic test packet; reject the corrupt marker
  // so the worker isolate exercises the corrupt-frame Logger.debug skip path.
  if (frame.length == 3 && frame[0] == 176 && frame[1] == 255 && frame[2] == 254) {
    return Int16List.fromList([0x0201, 0x0403]);
  }
  throw const FormatException('Corrupt Opus frame');
}

Int16List _decodeView(Uint8List frame, int sampleRate, int channels) {
  final backing = Int16List.fromList([0x1111, 0x0201, 0x0403, 0x5555]);
  return Int16List.sublistView(backing, 1, 3);
}

// Captures only sendable state. The CPU-bound interval must not block UI timers.
OpusFrameDecoder _busyDecoder(SendPort events) {
  return (frame, sampleRate, channels) {
    events.send('started');
    final clock = Stopwatch()..start();
    while (clock.elapsedMilliseconds < 300) {}
    events.send('finished');
    return Int16List.fromList([0x0201, 0x0403]);
  };
}

void main() {
  late AudioPlayerUtils player;

  setUp(() {
    player = AudioPlayerUtils.instance;
  });

  group('canPlayOrShare', () {
    Wal makeWal({String? filePath, List<List<int>>? data, WalStorage storage = WalStorage.mem}) {
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
      final wal = makeWal();
      expect(player.canPlayOrShare(wal), isFalse);
    });

    test('returns false when filePath empty string, data empty, storage mem', () {
      final wal = makeWal(filePath: '');
      expect(player.canPlayOrShare(wal), isFalse);
    });

    test('returns true when filePath is non-empty', () {
      final wal = makeWal(filePath: '/path/to/audio.wav');
      expect(player.canPlayOrShare(wal), isTrue);
    });

    test('returns true when data is non-empty', () {
      final wal = makeWal(
        data: [
          [1, 2, 3],
        ],
      );
      expect(player.canPlayOrShare(wal), isTrue);
    });

    test('returns true when storage is sdcard', () {
      final wal = makeWal(storage: WalStorage.sdcard);
      expect(player.canPlayOrShare(wal), isTrue);
    });

    test('returns true when filePath null but data present', () {
      final wal = makeWal(
        filePath: null,
        data: [
          [0xFF],
        ],
      );
      expect(player.canPlayOrShare(wal), isTrue);
    });

    test('returns true when all conditions met', () {
      final wal = makeWal(
        filePath: '/audio.wav',
        data: [
          [1],
        ],
        storage: WalStorage.sdcard,
      );
      expect(player.canPlayOrShare(wal), isTrue);
    });

    test('returns false for disk storage with no file or data', () {
      final wal = makeWal(storage: WalStorage.disk);
      expect(player.canPlayOrShare(wal), isFalse);
    });
  });

  group('readLengthPrefixedFrames (production streaming reader)', () {
    /// The persisted WAL framing format:
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

    test('round-trip: serialize then parse 320-byte PCM16 frames via production parser', () async {
      final frame1 = List<int>.generate(320, (i) => i & 0xFF);
      final frame2 = List<int>.generate(320, (i) => (i + 100) & 0xFF);
      final frame3 = List<int>.generate(320, (i) => (i + 200) & 0xFF);

      final serialized = serializeFrames([frame1, frame2, frame3]);
      expect(serialized.length, equals(3 * (4 + 320)));

      // Uses the PRODUCTION parseLengthPrefixedFrames function
      final parsed = await readLengthPrefixedFrames(Stream.value(serialized)).toList();
      expect(parsed.length, equals(3));
      expect(parsed[0], equals(Uint8List.fromList(frame1)));
      expect(parsed[1], equals(Uint8List.fromList(frame2)));
      expect(parsed[2], equals(Uint8List.fromList(frame3)));
    });

    test('production parser handles adversarial payload bytes correctly', () async {
      // Two 320-byte frames filled with 0xAA — if offset were wrong,
      // parser would read 0xAAAAAAAA as length and fail
      final frame1 = List<int>.generate(320, (i) => 0xAA);
      final frame2 = List<int>.generate(320, (i) => 0xBB);

      final serialized = serializeFrames([frame1, frame2]);
      final parsed = await readLengthPrefixedFrames(Stream.value(serialized)).toList();
      expect(parsed.length, equals(2));
      expect(parsed[0], equals(Uint8List.fromList(frame1)));
      expect(parsed[1], equals(Uint8List.fromList(frame2)));
    });

    test('variable-length frames round-trip via production parser', () async {
      final frames = [
        List<int>.generate(320, (i) => 0xAA),
        List<int>.generate(160, (i) => 0xBB),
        List<int>.generate(320, (i) => 0xCC),
      ];

      final serialized = serializeFrames(frames);
      final parsed = await readLengthPrefixedFrames(Stream.value(serialized)).toList();

      expect(parsed.length, equals(3));
      expect(parsed[0].length, equals(320));
      expect(parsed[1].length, equals(160));
      expect(parsed[2].length, equals(320));
      expect(parsed[0].every((b) => b == 0xAA), isTrue);
      expect(parsed[1].every((b) => b == 0xBB), isTrue);
      expect(parsed[2].every((b) => b == 0xCC), isTrue);
    });

    test('single frame round-trip via production parser', () async {
      final frame = List<int>.generate(320, (i) => 0xFF);
      final serialized = serializeFrames([frame]);
      final parsed = await readLengthPrefixedFrames(Stream.value(serialized)).toList();
      expect(parsed.length, equals(1));
      expect(parsed[0], equals(Uint8List.fromList(frame)));
    });

    test('prefix and payload can span arbitrary read chunks', () async {
      final raw = serializeFrames([
        [1, 2, 3],
        [4, 5]
      ]);
      final parsed = await readLengthPrefixedFrames(Stream.fromIterable([
        raw.sublist(0, 1),
        raw.sublist(1, 5),
        raw.sublist(5, 8),
        raw.sublist(8),
      ])).toList();
      expect(parsed, [
        [1, 2, 3],
        [4, 5]
      ]);
    });

    test('empty input returns no frames', () async {
      final parsed = await readLengthPrefixedFrames(Stream.value(Uint8List(0))).toList();
      expect(parsed.length, equals(0));
    });

    test('truncated length prefix returns no frames', () async {
      final parsed = await readLengthPrefixedFrames(Stream.value(Uint8List.fromList([0x40, 0x01, 0x00]))).toList();
      expect(parsed.length, equals(0));
    });

    test('truncated payload returns no frames', () async {
      // Length says 320 but only 10 bytes of payload
      final data = Uint8List.fromList([
        ...Uint32List.fromList([320]).buffer.asUint8List(),
        ...List.filled(10, 0xAA),
      ]);
      final parsed = await readLengthPrefixedFrames(Stream.value(data)).toList();
      expect(parsed.length, equals(0));
    });
  });

  group('writeRecordingWav', () {
    late Directory dir;
    late List<String> shares;

    setUp(() async {
      TestWidgetsFlutterBinding.ensureInitialized();
      dir = await Directory.systemTemp.createTemp('recording_wav_');
      shares = [];
      final mainName = Isolate.current.debugName;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('dev.fluttercommunity.plus/share'),
        (call) async {
          expect(Isolate.current.debugName, mainName);
          final paths = (call.arguments as Map)['paths'] as List;
          for (final path in paths.cast<String>()) {
            expect(await File(path).length(), greaterThan(44));
            shares.add(path);
          }
          return ''; // Native sheet dismissed; output must remain readable by receiving apps.
        },
      );
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (call) async => dir.path,
      );
    });

    tearDown(() async {
      player.debugOpusFrameDecoder = null;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('dev.fluttercommunity.plus/share'),
        null,
      );
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        null,
      );
      await dir.delete(recursive: true);
    });

    /// A phone-local PCM16 file whose single frame is [samples], in the WAL on-disk frame format.
    Future<Wal> pcmFile(int timerStart, List<int> samples) async {
      final name = 'audio_$timerStart.bin';
      final frame = Uint8List.fromList(samples);
      final bytes = BytesBuilder()
        ..add((ByteData(4)..setUint32(0, frame.length, Endian.little)).buffer.asUint8List())
        ..add(frame);
      await File('${dir.path}/$name').writeAsBytes(bytes.takeBytes());
      return Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.pcm16,
        seconds: 10,
        filePath: name,
        storage: WalStorage.disk,
        device: 'pendant',
      );
    }

    test('joins a recording\'s files into one WAV, oldest first', () async {
      final later = await pcmFile(2010, [3, 3, 4, 4]);
      final earlier = await pcmFile(2000, [1, 1, 2, 2]);
      final stillOnDevice = Wal(timerStart: 2020, codec: BleAudioCodec.pcm16, seconds: 10, storage: WalStorage.sdcard);

      final out = await player.writeRecordingWav([later, stillOnDevice, earlier], outputPath: '${dir.path}/out.wav');

      final wav = await out!.readAsBytes();
      expect(String.fromCharCodes(wav.sublist(0, 4)), 'RIFF');
      expect(ByteData.sublistView(wav).getUint32(40, Endian.little), 8,
          reason: 'both files\' PCM, nothing from the device');
      expect(wav.sublist(44), [1, 1, 2, 2, 3, 3, 4, 4]);
      expect(player.lastWorkerIsolateName, equals('writeRecordingWav'));
      expect(player.lastWorkerIsolateName, isNot(equals(Isolate.current.debugName)));
    });

    test('decodes single WAL audio file on a background isolate', () async {
      final wal = await pcmFile(2500, [5, 6, 7, 8]);
      final path = await player.ensureAudioFileExists(wal);

      expect(path, isNotNull);
      final wav = await File(path!).readAsBytes();
      expect(String.fromCharCodes(wav.sublist(0, 4)), 'RIFF');
      expect(wav.sublist(44), [5, 6, 7, 8]);
      expect(player.lastWorkerIsolateName, equals('decodeWalAudio'));
      expect(player.lastWorkerIsolateName, isNot(equals(Isolate.current.debugName)));
    });

    test('decodes Opus frames and safely runs Logger.debug skip paths in background isolate', () async {
      player.debugOpusFrameDecoder = _decodeTestOpusFrame;
      const opusName = 'audio_2600.bin';
      final opusBytes = BytesBuilder();
      for (final frame in <List<int>>[
        [176, 255, 254],
        [0xFF],
        [176, 255, 254],
      ]) {
        opusBytes
          ..add((ByteData(4)..setUint32(0, frame.length, Endian.little)).buffer.asUint8List())
          ..add(frame);
      }
      await File('${dir.path}/$opusName').writeAsBytes(opusBytes.takeBytes());
      final opusWal = Wal(
        timerStart: 2600,
        codec: BleAudioCodec.opus,
        seconds: 10,
        filePath: opusName,
        storage: WalStorage.disk,
        device: 'omi',
      );

      final corruptPartWal = await pcmFile(2610, [9, 9, 9, 9]);
      final cachedCorruptPath = await player.ensureAudioFileExists(corruptPartWal);
      await File(cachedCorruptPath!).writeAsBytes([0, 1, 2, 3]);

      final validLaterWal = await pcmFile(2620, [5, 6, 7, 8]);
      final out = await player.writeRecordingWav(
        [opusWal, corruptPartWal, validLaterWal],
        outputPath: '${dir.path}/opus_out.wav',
      );

      expect(out, isNotNull);
      final wav = await out!.readAsBytes();
      expect(String.fromCharCodes(wav.sublist(0, 4)), 'RIFF');
      expect(wav.sublist(44), [1, 2, 3, 4, 1, 2, 3, 4, 5, 6, 7, 8]);
      expect(player.lastWorkerIsolateName, equals('writeRecordingWav'));
      expect(player.lastWorkerIsolateName, isNot(equals(Isolate.current.debugName)));
    });

    test('cleans decoded parts after success and preserves playback cache and source', () async {
      final cached = await pcmFile(2700, [1, 2, 3, 4]);
      final path = await player.ensureAudioFileExists(cached);
      final uncached = await pcmFile(2710, [5, 6, 7, 8]);
      final before = (await dir.list().map((e) => e.path).toList()).toSet();
      final out = '${dir.path}/clean.wav';
      await player.writeRecordingWav([uncached, cached], outputPath: out);
      expect((await dir.list().map((e) => e.path).toList()).toSet(), {...before, out});
      expect(await File(path!).exists(), isTrue);
      expect(await File('${dir.path}/audio_2710.bin').exists(), isTrue);
    });

    test('format failure preserves previous export and cleans only job-owned scratch', () async {
      final a = await pcmFile(2800, [1, 2]);
      final b = await pcmFile(2810, [3, 4]);
      b.sampleRate = 8000;
      final out = File('${dir.path}/previous.wav');
      await out.writeAsBytes([42]);
      final before = (await dir.list().map((e) => e.path).toList()).toSet();
      await expectLater(player.writeRecordingWav([a, b], outputPath: out.path), throwsException);
      expect(await out.readAsBytes(), [42]);
      expect((await dir.list().map((e) => e.path).toList()).toSet(), before);
      b.sampleRate = 16000;
      expect(await player.writeRecordingWav([a, b], outputPath: out.path), isNotNull,
          reason: 'a failed export can be retried without touching its inputs');
    });

    test('memory-backed audio is decoded without leaking serialized input or WAV parts', () async {
      final wal = Wal(
          timerStart: 2900,
          codec: BleAudioCodec.pcm16,
          seconds: 1,
          data: [
            [1, 2, 3, 4]
          ],
          storage: WalStorage.mem);
      final out = '${dir.path}/memory.wav';
      await player.writeRecordingWav([wal], outputPath: out);
      expect((await File(out).readAsBytes()).sublist(44), [1, 2, 3, 4]);
      expect(await dir.list().map((e) => e.path).toList(), [out]);
      expect(
          wal.data,
          [
            [1, 2, 3, 4]
          ],
          reason: 'export must not consume the capture buffer');
    });

    test('UI events continue during production memory-backed Opus export', () async {
      final events = ReceivePort();
      var decoding = false;
      var ticks = 0;
      final subscription = events.listen((event) => decoding = event == 'started');
      final timer = Timer.periodic(const Duration(milliseconds: 5), (_) {
        if (decoding) ticks++;
      });
      player.debugOpusFrameDecoder = _busyDecoder(events.sendPort);
      try {
        final wal = Wal(
            timerStart: 2950,
            codec: BleAudioCodec.opus,
            seconds: 1,
            data: [
              [176, 255, 254]
            ],
            storage: WalStorage.mem);
        final out = await player.writeRecordingWav([wal], outputPath: '${dir.path}/responsive.wav');
        expect(out, isNotNull);
        expect(ticks, greaterThan(0), reason: 'CPU decode must run while UI timers are serviced');
      } finally {
        timer.cancel();
        await subscription.cancel();
        events.close();
      }
    });

    test('single and whole-recording sharing invoke the platform on main with complete files', () async {
      final wal = await pcmFile(2960, [1, 2, 3, 4]);
      await player.shareAsAudio(wal);
      await player.shareRecordingAsAudio([wal]);
      expect(shares, hasLength(2));
      for (final path in shares) {
        expect((await File(path).readAsBytes()).sublist(44), [1, 2, 3, 4]);
      }
    });

    test('worker failure never opens a share sheet and leaves no export scratch', () async {
      final a = await pcmFile(2970, [1, 2]);
      final b = await pcmFile(2980, [3, 4]);
      b.sampleRate = 8000;
      final before = (await dir.list().map((e) => e.path).toList()).toSet();
      await expectLater(player.shareRecordingAsAudio([a, b]), throwsException);
      expect(shares, isEmpty);
      expect((await dir.list().map((e) => e.path).toList()).toSet(), before);
    });

    test('concurrent recording shares publish independent files', () async {
      final a = await pcmFile(2990, [1, 2]);
      final b = await pcmFile(2991, [3, 4]);
      await Future.wait([
        player.shareRecordingAsAudio([a]),
        player.shareRecordingAsAudio([a, b])
      ]);
      expect(shares.toSet(), hasLength(2));
      final sizes = await Future.wait(shares.map((p) => File(p).length()));
      expect(sizes, unorderedEquals([46, 48]));
    });

    test('zero-length Opus payloads never become synthesized audio', () async {
      player.debugOpusFrameDecoder = _decodeView;
      await File('${dir.path}/zero.bin').writeAsBytes([0, 0, 0, 0]);
      final disk =
          Wal(timerStart: 2992, codec: BleAudioCodec.opus, seconds: 1, filePath: 'zero.bin', storage: WalStorage.disk);
      final memory = Wal(timerStart: 2993, codec: BleAudioCodec.opus, seconds: 1, data: [[]], storage: WalStorage.mem);
      expect(await player.writeRecordingWav([disk, memory], outputPath: '${dir.path}/zero.wav'), isNull);
      expect(await dir.list().map((e) => e.path).toList(), ['${dir.path}/zero.bin']);
    });

    test('decoder typed-list view excludes unrelated backing samples', () async {
      player.debugOpusFrameDecoder = _decodeView;
      final memory = Wal(
          timerStart: 2994,
          codec: BleAudioCodec.opus,
          seconds: 1,
          data: [
            [1]
          ],
          storage: WalStorage.mem);
      final out = await player.writeRecordingWav([memory], outputPath: '${dir.path}/view.wav');
      expect((await out!.readAsBytes()).sublist(44), [1, 2, 3, 4]);
    });

    test('empty Opus disk file needs no native decoder and creates no output', () async {
      await File('${dir.path}/empty.bin').writeAsBytes([]);
      final wal =
          Wal(timerStart: 2995, codec: BleAudioCodec.opus, seconds: 1, filePath: 'empty.bin', storage: WalStorage.disk);
      expect(await player.writeRecordingWav([wal], outputPath: '${dir.path}/empty.wav'), isNull);
      expect(await dir.list().map((e) => e.path).toList(), ['${dir.path}/empty.bin']);
    });

    test('returns null when no file in the recording has audio on the phone', () async {
      final onDevice = Wal(timerStart: 3000, codec: BleAudioCodec.pcm16, seconds: 10, storage: WalStorage.disk);

      expect(await player.writeRecordingWav([onDevice], outputPath: '${dir.path}/out.wav'), isNull);
    });
  });
}
