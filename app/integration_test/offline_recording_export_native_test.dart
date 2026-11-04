import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/audio_player_utils.dart';

/// Synthetic local audio only. Runs the production native Opus loader in a fresh worker
/// isolate, production WAL framing, combining and publication. No decoder seam or backend.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('exports 3601 seconds of mixed native Opus/PCM while UI frames advance', (tester) async {
    final docs = await getApplicationDocumentsDirectory();
    final temp = await getTemporaryDirectory();
    final owned = await temp.createTemp('offline-export-native-');
    final token = owned.uri.pathSegments.where((s) => s.isNotEmpty).last;
    final opusInput = File('${docs.path}/${token}_opus.bin');
    final pcmInput = File('${docs.path}/${token}_pcm.bin');
    final zeroInput = File('${docs.path}/${token}_zero.bin');
    addTearDown(() async {
      if (await opusInput.exists()) await opusInput.delete();
      if (await pcmInput.exists()) await pcmInput.delete();
      if (await zeroInput.exists()) await zeroInput.delete();
      await owned.delete(recursive: true);
    });

    initOpus(await opus_flutter.load());
    final encoder = SimpleOpusEncoder(sampleRate: 16000, channels: 1, application: Application.audio);
    late Uint8List packet;
    try {
      packet = encoder.encode(input: Int16List(320)); // 20 ms native silence.
    } finally {
      encoder.destroy();
    }
    await _writeFrames(opusInput, packet, 90000); // 1800 seconds.
    await _writeFrames(pcmInput, Uint8List(32000)..fillRange(0, 32000, 7), 1801);
    final opus = Wal(
        timerStart: 2000, codec: BleAudioCodec.opus, seconds: 1800, filePath: opusInput.path, storage: WalStorage.disk);
    final pcm = Wal(
        timerStart: 3800, codec: BleAudioCodec.pcm16, seconds: 1801, filePath: pcmInput.path, storage: WalStorage.disk);
    final player = AudioPlayerUtils.instance;
    expect(player.debugOpusFrameDecoder, isNull);
    var uiFrames = 0;
    final clock = Stopwatch()..start();
    final future = player.writeRecordingWav([pcm, opus], outputPath: '${owned.path}/complete.wav');
    var finished = false;
    final completion = future.whenComplete(() => finished = true);
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: Text('Exporting synthetic recording'))));
    while (!finished) {
      await tester.pump(const Duration(milliseconds: 16));
      // A real frame on the UI isolate must be runnable while native decode/combine is in flight.
      uiFrames++;
      await Future<void>.delayed(const Duration(milliseconds: 16));
    }
    final output = (await completion)!;
    final handle = await output.open();
    try {
      final header = await handle.read(44);
      expect(ByteData.sublistView(header).getUint32(40, Endian.little), 3601 * 32000);
      expect(await output.length(), 44 + 3601 * 32000);
      expect(await handle.read(32), everyElement(0), reason: 'oldest Opus silence precedes PCM');
      await handle.setPosition(44 + 1800 * 32000);
      expect(await handle.read(32), everyElement(7), reason: 'later PCM follows all Opus samples');
    } finally {
      await handle.close();
    }
    expect(uiFrames, greaterThan(2));
    expect(player.lastWorkerIsolateName, 'writeRecordingWav');

    // Real native single-file path, including fresh-isolate library initialization.
    final short = Wal(timerStart: 6000, codec: BleAudioCodec.opus, seconds: 1, data: [packet], storage: WalStorage.mem);
    final playback = (await player.ensureAudioFileExists(short))!;
    expect(await File(playback).length(), 44 + 640);
    await File(playback).delete();
    // A zero-length WAL packet must not ask native Opus for packet-loss concealment.
    await zeroInput.writeAsBytes([0, 0, 0, 0]);
    final emptyDisk = Wal(
        timerStart: 6100, codec: BleAudioCodec.opus, seconds: 1, filePath: zeroInput.path, storage: WalStorage.disk);
    final emptyMemory =
        Wal(timerStart: 6101, codec: BleAudioCodec.opus, seconds: 1, data: [[]], storage: WalStorage.mem);
    expect(await player.writeRecordingWav([emptyDisk, emptyMemory], outputPath: '${owned.path}/empty.wav'), isNull);
    expect(await opusInput.exists(), isTrue);
    expect(await pcmInput.exists(), isTrue);
    expect(await owned.list().map((e) => e.path).toList(), [output.path]);
    // ignore: avoid_print
    print('OFFLINE_EXPORT_NATIVE platform=${Platform.operatingSystem} seconds=3601 '
        'wav_bytes=${await output.length()} ui_frames=$uiFrames elapsed_ms=${clock.elapsedMilliseconds} '
        'opus=${getOpusVersion()}');
  }, timeout: const Timeout(Duration(minutes: 5)));
}

Future<void> _writeFrames(File file, Uint8List frame, int count) async {
  final encoded = BytesBuilder()
    ..add((ByteData(4)..setUint32(0, frame.length, Endian.little)).buffer.asUint8List())
    ..add(frame);
  final bytes = encoded.takeBytes();
  final output = await file.open(mode: FileMode.write);
  try {
    for (var i = 0; i < count; i++) {
      await output.writeFrom(bytes);
    }
  } finally {
    await output.close();
  }
}
