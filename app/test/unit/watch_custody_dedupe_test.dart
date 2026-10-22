import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/native_recording_intake.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/watch_live_coverage.dart';
import 'package:omi/services/wals/wal_frame_encoder.dart';
import '../support/custody_test_helpers.dart';

void main() {
  late Directory dir;
  late WatchLiveCoverage coverage;
  const start = 1792454400;
  const session = '0123456789abcdef0123456789abcdef';
  const name = 'audio_omibatchwatch${session}s0_pcm16_16000_1_fs160_$start.bin';
  setUp(() async {
    dir = await custodyDirectory();
    coverage = WatchLiveCoverage(() async => dir, now: () => DateTime.fromMillisecondsSinceEpoch((start + 100) * 1000));
    await File('${dir.path}/$name').writeAsBytes(encodeWalFrames(List.generate(100, (_) => List.filled(320, 0))));
    await Directory('${dir.path}/.watch-receipts').create();
    await File('${dir.path}/.watch-receipts/$name').writeAsString(jsonEncode({
      'metadata': {'version': 1, 'sessionID': session, 'segment': 0, 'startedAt': start, 'ownerUID': 'owner'},
      'digest': 'a' * 64
    }));
  });
  tearDown(() async {
    await dir.delete(recursive: true);
  });

  test('covered Watch copy is deleted without upload and native receipt stays', () async {
    await coverage.record('owner', start.toDouble(), start + .5);
    await coverage.record('owner', start + .4, start + .95);
    final ledger = await custodyLedger();
    await NativeRecordingIntake(ledger, coverage: coverage, dedupeOff: () async => false).scan();
    expect(await File('${dir.path}/$name').exists(), isFalse);
    expect(await File('${dir.path}/.watch-receipts/$name').exists(), isTrue);
    expect(await ledger.getAllWals(), isEmpty);
    final restored =
        WatchLiveCoverage(() async => dir, now: () => DateTime.fromMillisecondsSinceEpoch((start + 100) * 1000));
    expect(await restored.covers('owner', start.toDouble(), start + 1), isTrue);
    expect(await restored.covers('other', start.toDouble(), start + 1), isFalse);
  });

  for (final mode in ['uncovered', 'kill-switch', 'flag-error', 'unknown']) {
    test('$mode keeps Watch audio in automatic, unbound custody', () async {
      if (mode != 'uncovered') await coverage.record('owner', start.toDouble(), start + 1);
      final ledger = await custodyLedger();
      await NativeRecordingIntake(ledger,
              coverage: coverage,
              dedupeOff: mode == 'unknown'
                  ? null
                  : () async {
                      if (mode == 'flag-error') throw StateError('flag');
                      return mode == 'kill-switch';
                    })
          .scan();
      final wal = (await ledger.getAllWals()).single;
      expect(wal.holdForUser, isFalse);
      expect(wal.recordingSessionId, isNull);
      expect(await File('${dir.path}/$name').exists(), isTrue);
    });
  }

  test('coverage below 95 percent, gaps and expired proof keep audio', () async {
    await coverage.record('owner', start.toDouble(), start + .94);
    expect(await coverage.covers('owner', start.toDouble(), start + 1), isFalse);
    final expired =
        WatchLiveCoverage(() async => dir, now: () => DateTime.fromMillisecondsSinceEpoch((start + 8 * 86400) * 1000));
    expect(await expired.covers('owner', start.toDouble(), start + 1), isFalse);
  });
  test('live Watch coverage is recorded only after file and ledger are durable', () async {
    final ledger = await custodyLedger();
    final live = Wal(
        timerStart: DateTime.now().millisecondsSinceEpoch ~/ 1000,
        codec: BleAudioCodec.pcm16,
        seconds: 1,
        device: 'watch-live',
        deviceType: DeviceType.appleWatch,
        ownerUid: 'owner',
        status: WalStatus.synced,
        storage: WalStorage.mem,
        totalFrames: 100,
        data: List.generate(100, (_) => List.filled(320, 0)));
    ledger.testWals = [live];
    expect(await ledger.watchCoverage.covers('owner', live.timerStart.toDouble(), live.timerStart + 1), isFalse);
    await ledger.syncAll();
    expect(live.storage, WalStorage.disk);
    expect(await ledger.hasDurableWal(live, admittedGeneration: ledger.sessionGeneration), isTrue);
    expect(await ledger.watchCoverage.covers('owner', live.timerStart.toDouble(), live.timerStart + 1), isTrue);
  });

  test('an index failure creates no Watch coverage proof', () async {
    final ledger = await custodyLedger(persist: (_) async => throw StateError('disk failure'));
    final live = Wal(
        timerStart: DateTime.now().millisecondsSinceEpoch ~/ 1000,
        codec: BleAudioCodec.pcm16,
        seconds: 1,
        device: 'watch-live',
        deviceType: DeviceType.appleWatch,
        ownerUid: 'owner',
        status: WalStatus.synced,
        storage: WalStorage.mem,
        totalFrames: 100,
        data: List.generate(100, (_) => List.filled(320, 0)));
    ledger.testWals = [live];
    await expectLater(ledger.syncAll(), throwsStateError);
    expect(await ledger.watchCoverage.covers('owner', live.timerStart.toDouble(), live.timerStart + 1), isFalse);
  });

  test('Watch checkpoint retains socket-sent frames before a minute receipt without ending the session', () async {
    final ledger = await custodyLedger();
    ledger.sourceDeviceType = DeviceType.appleWatch;
    ledger.setActiveRecordingSessionId('live-session');
    await ledger.onAudioCodecChanged(BleAudioCodec.pcm16, deviceInfo: (id: 'apple-watch', model: 'Watch9,1'));
    for (var i = 0; i < 100; i++) {
      final key = FrameSyncKey.fromIndex(i);
      ledger.onFrameCaptured(WalFrame(payload: List.filled(320, 0), syncKey: key));
      ledger.markFrameSynced(key);
    }
    await ledger.checkpointWatchAudio();
    final live = (await ledger.getAllWals()).single;
    expect(live.deviceType, DeviceType.appleWatch);
    expect(live.totalFrames, 100);
    expect(live.recordingSessionId, 'live-session');
    expect(await ledger.watchCoverage.covers('owner', live.timerStart.toDouble(), live.timerStart + 1), isTrue);
  });
}
