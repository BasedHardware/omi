import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/audio/wav_combiner.dart';
import 'package:omi/utils/audio_player_utils.dart';

Uint8List _testBackgroundOpusDecoder(int sampleRate, int channels, Uint8List opusFrame) {
  if (Isolate.current.debugName == 'main') {
    throw StateError('Opus decode ran on the UI isolate instead of a background isolate');
  }
  if (opusFrame.isNotEmpty && opusFrame.first == 0xFF) {
    throw const FormatException('Corrupted Opus frame');
  }
  return Uint8List.fromList([
    for (final byte in opusFrame) ...[byte, byte],
  ]);
}

void main() {
  late AudioPlayerUtils player;
  late Directory dir;

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    player = AudioPlayerUtils.instance;
    player.opusFrameDecoder = _testBackgroundOpusDecoder;
    dir = await Directory.systemTemp.createTemp('audio_isolate_decode_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => dir.path,
    );
  });

  tearDown(() async {
    player.opusFrameDecoder = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (await dir.exists()) {
      await dir.delete(recursive: true);
    }
  });

  Future<Wal> framedWalFile(
    int timerStart,
    List<List<int>> frames, {
    BleAudioCodec codec = BleAudioCodec.pcm16,
    int sampleRate = 16000,
  }) async {
    final name = 'audio_$timerStart.bin';
    final bytes = BytesBuilder();
    for (final rawFrame in frames) {
      final frame = Uint8List.fromList(rawFrame);
      final lenBytes = (ByteData(4)..setUint32(0, frame.length, Endian.little)).buffer.asUint8List();
      bytes.add(lenBytes);
      bytes.add(frame);
    }
    await File('${dir.path}/$name').writeAsBytes(bytes.takeBytes());
    return Wal(
      timerStart: timerStart,
      codec: codec,
      sampleRate: sampleRate,
      seconds: 10,
      filePath: name,
      storage: WalStorage.disk,
      device: 'pendant',
    );
  }

  test('decodes Opus and PCM WALs in a background isolate and combines WAV parts off the UI isolate', () async {
    final opusWal = await framedWalFile(
      4000,
      [
        [0xFF, 0x00],
        [0x10, 0x20],
      ],
      codec: BleAudioCodec.opus,
    );
    final pcmWal = await framedWalFile(
      4010,
      [
        [0x30, 0x30, 0x40, 0x40],
      ],
      codec: BleAudioCodec.pcm16,
    );

    final opusWavPath = await player.ensureAudioFileExists(opusWal);
    expect(opusWavPath, isNotNull);
    expect(player.lastDecodeIsolateDebugName, 'decodeWalAudio');

    final pcmWavPath = await player.ensureAudioFileExists(pcmWal);
    expect(pcmWavPath, isNotNull);
    expect(player.lastDecodeIsolateDebugName, 'decodeWalAudio');

    final corruptPart = File('${dir.path}/corrupt.wav');
    corruptPart.writeAsBytesSync([1, 2, 3, 4]);
    final combined = await WavCombiner.combineWavFiles(
      [File(opusWavPath!), corruptPart, File(pcmWavPath!)],
      '${dir.path}/combined.wav',
    );

    expect(WavCombiner.lastCombineIsolateDebugName, 'combineWavFiles');
    final wav = await combined.readAsBytes();
    expect(String.fromCharCodes(wav.sublist(0, 4)), 'RIFF');
    expect(ByteData.sublistView(wav).getUint32(40, Endian.little), 8);
    expect(wav.sublist(44), [0x10, 0x10, 0x20, 0x20, 0x30, 0x30, 0x40, 0x40]);
  });

  test('propagates background worker failure when WAV parts have incompatible sample rates', () async {
    final wal16k = await framedWalFile(
      5000,
      [
        [1, 1, 2, 2],
      ],
      sampleRate: 16000,
    );
    final wal8k = await framedWalFile(
      5010,
      [
        [3, 3, 4, 4],
      ],
      sampleRate: 8000,
    );

    final wav16k = await player.ensureAudioFileExists(wal16k);
    final wav8k = await player.ensureAudioFileExists(wal8k);
    final outputPath = '${dir.path}/incompatible.wav';

    await expectLater(
      WavCombiner.combineWavFiles([File(wav16k!), File(wav8k!)], outputPath),
      throwsException,
    );
    expect(await File(outputPath).exists(), isFalse);
  });
}
