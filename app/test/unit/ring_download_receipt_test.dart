import 'dart:io';
import 'package:crypto/crypto.dart';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/wal_file_manager.dart';

import 'pendant_ring_custody_test.dart' show v1Info;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  late PendantCustodyStore store;
  final managers = <PendantRingCustody>[];

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('ring_download_receipts_');
    SharedPreferences.setMockInitialValues({'uid': 'owner'});
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => directory.path,
    );
    await WalFileManager.init();
    await WalFileManager.saveWals([]);
    store = PendantCustodyStore(directoryProvider: () async => Directory('${directory.path}/custody'));
  });

  tearDown(() async {
    for (final manager in managers) {
      await manager.flush();
    }
    managers.clear();
    await store.flush();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    await directory.delete(recursive: true);
  });

  PendantRingCustody manager({CustodyWalValidator? validator}) {
    final result = PendantRingCustody(store: store, walValidator: validator);
    managers.add(result);
    return result;
  }

  Future<(Wal, CustodyWalRef)> audio(String name, {int start = 100, int end = 120}) async {
    final file = File('${directory.path}/$name');
    await file.writeAsBytes([1, 17], flush: true);
    final wal = Wal(
        codec: BleAudioCodec.opus,
        timerStart: 1000,
        seconds: 1,
        totalFrames: 1,
        filePath: name,
        storage: WalStorage.disk,
        status: WalStatus.miss,
        ownerUid: 'owner',
        device: 'device',
        downloadRingId: 7,
        downloadSeqStart: start,
        downloadSeqEnd: end,
        downloadFileBytes: 2,
        fileSha256: sha256.convert([1, 17]).toString());
    return (
      wal,
      CustodyWalRef(
          fileName: name,
          bytes: 2,
          frames: 1,
          ownerUid: 'owner',
          downloadDeviceId: 'device',
          downloadRingId: 7,
          downloadSeqStart: start,
          downloadSeqEnd: end,
          fileSha256: sha256.convert([1, 17]).toString())
    );
  }

  test('R16b 10002-row read snapshot hashes only notification overlaps and rechecks changed bytes', () async {
    final a = await audio('island-a.bin', start: 110, end: 111);
    final b = await audio('island-b.bin', start: 120, end: 121);
    final indexed = [
      a.$1,
      b.$1,
      for (var i = 0; i < 10000; i++)
        Wal(
            timerStart: 1000 + i,
            codec: BleAudioCodec.opus,
            seconds: 1,
            filePath: 'unrelated-$i.bin',
            storage: WalStorage.disk,
            status: WalStatus.miss)
    ];
    await WalFileManager.saveWals(indexed);
    var loads = 0, hashes = 0;
    final c = PendantRingCustody(
        store: store,
        indexLoader: () async {
          loads++;
          return WalFileManager.loadIndexedWals();
        },
        fileDigest: (file) async {
          hashes++;
          return (await sha256.bind(file.openRead()).first).toString();
        });
    managers.add(c);
    await c.beginConnection('device', 1, v1Info(readSeq: 100, writeSeq: 130));
    await c.recordDurableRingRange('device', 1, 7, 110, 111, [a.$2]);
    await c.recordDurableRingRange('device', 1, 7, 120, 121, [b.$2]);
    loads = 0;
    hashes = 0;
    final validate = await c.createReadValidator();
    for (var seq = 100; seq < 121; seq++) {
      expect(await c.validatedRecordRanges('device', 1, 7, startSeq: seq, endSeq: seq + 1, readValidator: validate),
          seq == 110 || seq == 120 ? [(seq, seq + 1)] : isEmpty);
    }
    expect(loads, 1, reason: 'one persisted index decode for this READ, not each DATA');
    expect(hashes, 2, reason: 'no hashing unrelated ranges or 10000 unrelated rows');
    await File('${directory.path}/island-a.bin').writeAsBytes([1, 18], flush: true);
    expect(await c.validatedRecordRanges('device', 1, 7, startSeq: 110, endSeq: 111, readValidator: validate), isEmpty);
    expect(hashes, 3, reason: 'suppression must hash fresh bytes, never cache a positive result');
  }, skip: !ringDrainRecoveryEnabled);

  test('R16b read snapshot rehashes before ADVANCE and rejects a revoked index', () async {
    final a = await audio('contiguous.bin', start: 100, end: 120);
    await WalFileManager.saveWals([a.$1]);
    var loads = 0, hashes = 0;
    final c = PendantRingCustody(
        store: store,
        indexLoader: () async {
          loads++;
          return WalFileManager.loadIndexedWals();
        },
        fileDigest: (file) async {
          hashes++;
          return (await sha256.bind(file.openRead()).first).toString();
        });
    managers.add(c);
    await c.beginConnection('device', 1, v1Info(readSeq: 100, writeSeq: 130));
    loads = 0;
    hashes = 0;
    final snapshot = await c.createReadValidator();
    expect(await c.validatedAdvanceTarget('device', 1, 7, readValidator: snapshot), 120);
    final firstHashes = hashes;
    expect(firstHashes, greaterThan(0));
    expect(await c.validatedAdvanceTarget('device', 1, 7, readValidator: snapshot), 120);
    expect(hashes, firstHashes * 2, reason: 'each ADVANCE decision hashes again');
    expect(loads, 1);
    await WalFileManager.saveWals([a.$1..status = WalStatus.corrupted]);
    expect(snapshot.isCurrent, isFalse);
    expect(await c.validatedAdvanceTarget('device', 1, 7, readValidator: snapshot), isNull);
    expect(await c.validatedRecordRanges('device', 1, 7, startSeq: 100, endSeq: 120, readValidator: snapshot), isEmpty);
    final refreshed = await c.createReadValidator();
    expect(await c.validatedAdvanceTarget('device', 1, 7, readValidator: refreshed), isNull);
    expect(loads, 2, reason: 'a new snapshot is explicit, never per notification');
  }, skip: !ringDrainRecoveryEnabled);

  test('synthetic slow ACK, fast buffered burst, disconnect and restart replay exact indexed prefix', () async {
    final first = await audio('slow.bin', end: 110);
    final burst = await audio('burst.bin', start: 110, end: 150);
    await WalFileManager.saveWals([first.$1]);
    final old = manager();
    await old.beginConnection('device', 1, v1Info(readSeq: 100, writeSeq: 200));
    await old.recordDurableRingRange('device', 1, 7, 100, 110, [first.$2]);
    expect(await old.validatedAdvanceTarget('device', 1, 7), 110);
    await old.markAdvanced('device', 1, 110);

    old.endConnection('device', 1);
    await WalFileManager.saveWals([first.$1, burst.$1]);
    // Disk/index completion belongs to the original READ, after live teardown.
    await old.recordDurableRingRange('device', 1, 7, 110, 150, [burst.$2]);
    await old.flush();
    final replay = <int>[];
    final restarted = manager();
    await restarted.beginConnection('device', 2, v1Info(readSeq: 110, writeSeq: 200), replayAdvance: (seq) async {
      replay.add(seq);
      return RingProtocol.ackOk;
    });
    expect(replay, [150]);
    expect(restarted.acknowledgedReadSeqFor('device', 2, 7), 150);
  }, skip: !ringDrainRecoveryEnabled);

  test('receipt without persisted WAL index never authorizes reclaim, then index enables replay', () async {
    final file = await audio('unindexed.bin');
    await manager().recordDurableRingRange('device', 1, 7, 100, 120, [file.$2]);
    final replay = <int>[];
    final next = manager();
    await next.beginConnection('device', 2, v1Info(readSeq: 100, writeSeq: 200), replayAdvance: (seq) async {
      replay.add(seq);
      return RingProtocol.ackOk;
    });
    expect(replay, isEmpty);
    expect(await next.validatedAdvanceTarget('device', 2, 7), isNull);
    await WalFileManager.saveWals([file.$1]);
    await next.restoreDownloadedRanges('device', 2, 7, reportedReadSeq: 100);
    expect(await next.validatedAdvanceTarget('device', 2, 7), 120);
  }, skip: !ringDrainRecoveryEnabled);

  test('missing older ref preserves newer proof but never bridges the missing prefix', () async {
    final valid = await audio('newer.bin', start: 110, end: 150);
    await WalFileManager.saveWals([valid.$1]);
    final old = manager();
    await old.recordDurableRingRange(
        'device', 1, 7, 100, 110, [const CustodyWalRef(fileName: 'missing.bin', bytes: 2, frames: 1)]);
    await old.recordDurableRingRange('device', 1, 7, 110, 150, [valid.$2]);
    final next = manager();
    await next.beginConnection('device', 2, v1Info(readSeq: 100, writeSeq: 200));
    expect(await next.validatedAdvanceTarget('device', 2, 7), isNull);
    final gap = await audio('gap.bin', end: 110);
    await WalFileManager.saveWals([valid.$1, gap.$1]);
    await next.recordDurableRingRange('device', 2, 7, 100, 110, [gap.$2]);
    expect(await next.validatedAdvanceTarget('device', 2, 7), 150);
  }, skip: !ringDrainRecoveryEnabled);

  test('an old epoch completing after a new grant joins only the same ring', () async {
    final file = await audio('late.bin');
    await WalFileManager.saveWals([file.$1]);
    final c = manager();
    await c.beginConnection('device', 1, v1Info(readSeq: 100, writeSeq: 200));
    c.endConnection('device', 1);
    await c.beginConnection('device', 2, v1Info(readSeq: 100, writeSeq: 200));
    await c.recordDurableRingRange('device', 1, 7, 100, 120, [file.$2]);
    expect(await c.validatedAdvanceTarget('device', 2, 7), 120);
    await c.beginConnection('device', 3, v1Info(readSeq: 100, writeSeq: 200, ringId: 8));
    await c.recordDurableRingRange('device', 1, 7, 120, 140, [file.$2]);
    expect(await c.validatedAdvanceTarget('device', 3, 8), isNull);
  }, skip: !ringDrainRecoveryEnabled);

  test('ACK does not erase receipt until fresh INFO confirms the device frontier', () async {
    final file = await audio('lost_ack.bin');
    await WalFileManager.saveWals([file.$1]);
    final c = manager();
    await c.beginConnection('device', 1, v1Info(readSeq: 100, writeSeq: 200));
    await c.recordDurableRingRange('device', 1, 7, 100, 120, [file.$2]);
    await c.markAdvanced('device', 1, 120);
    final replay = <int>[];
    await manager().beginConnection('device', 2, v1Info(readSeq: 100, writeSeq: 200), replayAdvance: (seq) async {
      replay.add(seq);
      return RingProtocol.ackOk;
    });
    expect(replay, [120]);
    final receipts = await store.updateDownloadedRanges('device', 7);
    expect(receipts, hasLength(1));
  }, skip: !ringDrainRecoveryEnabled);

  test('ACK retires old refs from the next target validation work', () async {
    final calls = <String>[];
    final c = manager(validator: (ref) async {
      calls.add(ref.fileName);
      return true;
    });
    await c.beginConnection('device', 1, v1Info(readSeq: 100, writeSeq: 200));
    for (var i = 0; i < 12; i++) {
      await c.recordDurableRingRange(
          'device', 1, 7, 100 + i, 101 + i, [CustodyWalRef(fileName: '$i.bin', bytes: 2, frames: 1)]);
      expect(await c.validatedAdvanceTarget('device', 1, 7), 101 + i);
      await c.markAdvanced('device', 1, 101 + i);
    }
    expect(calls.length, 12, reason: 'one new ref per target, rather than 1+2+...+12 index loads');
  }, skip: !ringDrainRecoveryEnabled);

  test('account change rejects an otherwise indexed receipt', () async {
    final file = await audio('foreign.bin');
    await WalFileManager.saveWals([file.$1]);
    await manager().recordDurableRingRange('device', 1, 7, 100, 120, [file.$2]);
    SharedPreferencesUtil().uid = 'other';
    final replay = <int>[];
    await manager().beginConnection('device', 2, v1Info(readSeq: 100, writeSeq: 200), replayAdvance: (seq) async {
      replay.add(seq);
      return RingProtocol.ackOk;
    });
    expect(replay, isEmpty);
  }, skip: !ringDrainRecoveryEnabled);

  test('pre-upgrade ring proof cannot replay an unscoped foreign WAL', () async {
    final file = await audio('legacy_foreign.bin');
    file.$1.ownerUid = 'previous-owner';
    await WalFileManager.saveWals([file.$1]);
    await store.saveJson('device', {
      'device_id': 'device',
      'ring_id': 7,
      'durable_seq': 100,
      'last_advanced_seq': 100,
      'reported_read_seq': 100,
      'reported_write_seq': 200,
      'live_ranges': [],
      // Before scoped download receipts, custody refs had no owner or ring scope.
      'ring_ranges': [
        {
          'start_seq': 100,
          'end_seq': 120,
          'wals': [
            {'file': 'legacy_foreign.bin', 'bytes': 2, 'frames': 1},
          ],
        },
      ],
    });

    final replay = <int>[];
    final next = manager();
    await next.beginConnection('device', 2, v1Info(readSeq: 100, writeSeq: 200), replayAdvance: (seq) async {
      replay.add(seq);
      return RingProtocol.ackOk;
    });

    expect(replay, isEmpty);
    expect(await next.validatedAdvanceTarget('device', 2, 7), isNull);
  }, skip: !ringDrainRecoveryEnabled);

  test('restart after index commit before custody receipt reconstructs exact range without downloading', () async {
    final file = await audio('index_is_journal.bin');
    file.$1
      ..device = 'device'
      ..downloadRingId = 7
      ..downloadSeqStart = 100
      ..downloadSeqEnd = 120
      ..downloadFileBytes = 2;
    await WalFileManager.saveWals([file.$1]);
    // No recordDurableRingRange/checkpoint write occurred before this restart.
    expect(await store.updateDownloadedRanges('device', 7), isEmpty);
    final replay = <int>[];
    await manager().beginConnection('device', 2, v1Info(readSeq: 100, writeSeq: 200), replayAdvance: (seq) async {
      replay.add(seq);
      return RingProtocol.ackOk;
    });
    expect(replay, [120]);
    final recovered = (await WalFileManager.loadIndexedWals()).single;
    expect(recovered.downloadFileBytes, 2);
    expect(recovered.downloadSeqEnd, 120);
  }, skip: !ringDrainRecoveryEnabled);

  test('truncated indexed download cannot reconstruct proof by measuring its new shorter length', () async {
    final file = await audio('truncated.bin');
    file.$1
      ..device = 'device'
      ..downloadRingId = 7
      ..downloadSeqStart = 100
      ..downloadSeqEnd = 120
      ..downloadFileBytes = 2;
    await WalFileManager.saveWals([file.$1]);
    await File('${directory.path}/truncated.bin').writeAsBytes([1], flush: true);
    final replay = <int>[];
    await manager().beginConnection('device', 2, v1Info(readSeq: 100, writeSeq: 200), replayAdvance: (seq) async {
      replay.add(seq);
      return RingProtocol.ackOk;
    });
    expect(replay, isEmpty);
  }, skip: !ringDrainRecoveryEnabled);

  test('an indexed coordinate mismatch cannot widen a downloaded range', () async {
    final file = await audio('coordinates.bin');
    file.$1
      ..device = 'device'
      ..downloadRingId = 7
      ..downloadSeqStart = 100
      ..downloadSeqEnd = 120
      ..downloadFileBytes = 2;
    await WalFileManager.saveWals([file.$1]);
    final ref = CustodyWalRef(
        fileName: 'coordinates.bin',
        bytes: 2,
        frames: 1,
        ownerUid: 'owner',
        downloadRingId: 7,
        downloadSeqStart: 100,
        downloadSeqEnd: 120,
        downloadDeviceId: 'device',
        fileSha256: sha256.convert([1, 17]).toString());
    expect(await walFileManagerCustodyValidator(ref), isTrue);
    final c = manager();
    await c.recordDurableRingRange('device', 1, 7, 100, 140, [ref]);
    expect(await store.updateDownloadedRanges('device', 7), isEmpty);
    final replay = <int>[];
    await c.beginConnection('device', 2, v1Info(readSeq: 100, writeSeq: 200), replayAdvance: (seq) async {
      replay.add(seq);
      return RingProtocol.ackOk;
    });
    expect(replay, [120], reason: 'only the exact indexed interval is reusable');
  }, skip: !ringDrainRecoveryEnabled);

  test('kill switch OFF retains the old disconnected-proof omission', () async {
    final c = manager(validator: (_) async => true);
    await c.beginConnection('device', 1, v1Info(readSeq: 100, writeSeq: 200));
    c.endConnection('device', 1);
    await c.recordDurableRingRange(
        'device', 1, 7, 100, 120, [const CustodyWalRef(fileName: 'old.bin', bytes: 2, frames: 1)]);
    expect(await store.updateDownloadedRanges('device', 7), isEmpty);
    final replay = <int>[];
    await c.beginConnection('device', 2, v1Info(readSeq: 100, writeSeq: 200), replayAdvance: (seq) async {
      replay.add(seq);
      return RingProtocol.ackOk;
    });
    expect(replay, isEmpty);
  }, skip: ringDrainRecoveryEnabled);
}
