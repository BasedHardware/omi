import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _TestTimer implements Timer {
  _TestTimer(this.callback);
  final void Function(Timer) callback;
  @override
  bool isActive = true;
  @override
  int tick = 0;
  void fire() {
    expect(isActive, isTrue);
    tick++;
    callback(this);
  }

  @override
  void cancel() => isActive = false;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory documents;
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'owner-a'});
    await SharedPreferencesUtil.init();
    documents = await Directory.systemTemp.createTemp('wal_startup_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (_) async => documents.path);
    await WalFileManager.init();
  });
  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await documents.delete(recursive: true);
  });

  Future<Wal> seedOldRow() async {
    final old = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_before_startup.bin');
    await File('${documents.path}/${old.filePath}').writeAsBytes([1, 2, 3]);
    await WalFileManager.saveWals([old]);
    return old;
  }

  test('a flush racing startup cannot seed an empty worker and forget loaded files', () async {
    final old = await seedOldRow();
    final loaded = Completer<void>();
    final releaseLoad = Completer<void>();
    final sync = LocalWalSyncImpl(_Listener(),
        deltaIndexAllowed: () async => true,
        loadWals: () async {
          final rows = await WalFileManager.loadWals();
          loaded.complete();
          await releaseLoad.future;
          return rows;
        });
    sync.start();
    await loaded.future;
    final stopping = sync.stop();
    await pumpEventQueue(times: 100);
    releaseLoad.complete();
    await sync.walReady;
    await stopping;
    final added = Wal(
        timerStart: 2,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_after_startup.bin');
    await File('${documents.path}/${added.filePath}').writeAsBytes([4, 5, 6]);
    await sync.addExternalWal(added, admittedGeneration: sync.sessionGeneration);
    addTearDown(() async => (await sync.indexWorkerForTesting)?.close());
    expect((await WalFileManager.loadIndexedWals()).map((w) => w.filePath), [old.filePath, added.filePath],
        reason: 'later deltas must retain files loaded at startup');
    expect(await File('${documents.path}/${old.filePath}').readAsBytes(), [1, 2, 3]);
  });
  for (final deltaWriter in [true, false]) {
    test('failed admission persists capture and retries on flush (delta=$deltaWriter)', () async {
      final old = await seedOldRow();
      final originalIndex = await File('${documents.path}/wals.json').readAsString();
      final timers = <_TestTimer>[];
      var recover = false;
      var loads = 0;
      final sync = LocalWalSyncImpl(_Listener(),
          freeDiskBytes: () async => 64 << 30,
          periodic: (_, callback) {
            final timer = _TestTimer(callback);
            timers.add(timer);
            return timer;
          },
          deltaIndexAllowed: () async => deltaWriter,
          loadWals: () async {
            loads++;
            if (!recover) throw const FileSystemException('injected admission failure');
            return WalFileManager.loadWals();
          });
      addTearDown(() async {
        await sync.stop();
        (await sync.indexWorkerForTesting)?.close();
      });
      sync.start();
      await pumpEventQueue(times: 30);
      expect(loads, 1);
      // Real capture and sealing must run despite the failed startup gate.
      final frame = sync.onFrameCaptured(WalFrame(payload: [7, 8, 9], syncKey: FrameSyncKey.fromIndex(1)));
      await sync.finalizeCurrentSession();
      final captured = sync.testWals.single;
      expect(captured.storage, WalStorage.disk);
      final capturedBytes = await File('${documents.path}/${captured.filePath}').readAsBytes();
      expect(capturedBytes, [3, 0, 0, 0, 7, 8, 9]);
      expect(sync.isFrameDurable(frame), isFalse, reason: 'audio fsync alone cannot prove indexed custody');
      expect(await File('${documents.path}/wals.json').readAsString(), originalIndex);
      expect(sync.indexWorkerForTesting, isNull);
      expect(timers.every((t) => t.isActive), isTrue);
      expect(loads, greaterThan(1), reason: 'the failed gate must be retried rather than cached forever');

      recover = true;
      timers[1].fire(); // The ordinary flush tick retries admission, without restarting capture.
      await sync.testWalIoQuiescent;
      await sync.walReady;
      expect(
          (await WalFileManager.loadIndexedWals()).map((w) => w.filePath).toSet(), {old.filePath, captured.filePath});
      expect(await File('${documents.path}/${old.filePath}').readAsBytes(), [1, 2, 3]);
      expect(await File('${documents.path}/${captured.filePath}').readAsBytes(), capturedBytes);
      expect(await sync.hasDurableWal(captured, admittedGeneration: sync.sessionGeneration), isTrue);
      expect(captured.data, isEmpty, reason: 'a recovered index save must release the fsynced payload');
      expect(sync.isFrameDurable(frame), isTrue);
      // A fresh ledger sees both rows after recovery; no directory scan adopts or deletes orphans.
      final restarted = LocalWalSyncImpl(_Listener());
      await restarted.loadForOnDeviceWorker();
      expect(restarted.testWals.map((w) => w.filePath).toSet(), {old.filePath, captured.filePath});
    });
  }
  test('legacy migration reload stays fenced until pending rows can be merged', () async {
    final old = await seedOldRow();
    final legacy = File('${documents.path}/audio_limitless_opus_16000_1_fs320_r1_1794870000000.bin');
    await legacy.writeAsBytes([4, 5, 6]);
    SharedPreferencesUtil().saveStringList('flash_page_pending_uploads', [legacy.path]);
    final enteredReload = Completer<void>();
    final releaseReload = Completer<void>();
    var loads = 0;
    final sync = LocalWalSyncImpl(_Listener(),
        deltaIndexAllowed: () async => true,
        loadWals: () async {
          final rows = await WalFileManager.loadWals();
          if (++loads == 2) {
            enteredReload.complete();
            await releaseReload.future;
          }
          return rows;
        });
    sync.start();
    await enteredReload.future;
    final added = Wal(
        timerStart: 2,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_during_migration.bin');
    await File('${documents.path}/${added.filePath}').writeAsBytes([7, 8, 9]);
    final adding = sync.addExternalWal(added, admittedGeneration: sync.sessionGeneration);
    try {
      await pumpEventQueue(times: 100);
      expect(sync.indexWorkerForTesting, isNull, reason: 'migration still owns the startup snapshot');
    } finally {
      releaseReload.complete();
      await adding;
      await sync.walReady;
      await sync.stop();
      (await sync.indexWorkerForTesting)?.close();
    }
    expect((await WalFileManager.loadIndexedWals()).map((w) => w.filePath).toSet(),
        {old.filePath, legacy.uri.pathSegments.last, added.filePath});
  });

  test('a repeated start during an initialization save cannot re-arm its own fence', () async {
    final old = await seedOldRow();
    old.storage = WalStorage.flashPage;
    old.status = WalStatus.synced;
    old.syncedAt = 1;
    await WalFileManager.saveWals([old]);
    SharedPreferencesUtil().autoRemoveSyncedCopies = true;
    final timers = <_TestTimer>[];
    var saves = 0;
    late LocalWalSyncImpl sync;
    sync = LocalWalSyncImpl(_Listener(), periodic: (_, callback) {
      final timer = _TestTimer(callback);
      timers.add(timer);
      return timer;
    }, persistWals: (rows) async {
      if (++saves == 1) sync.start(); // Re-enter after admission, before the startup tail finishes.
      await WalFileManager.saveWals(rows);
    });
    addTearDown(() {
      for (final timer in timers) {
        timer.cancel();
      }
    });
    sync.start();
    await sync.walReady.timeout(const Duration(seconds: 2));
    expect(saves, 2, reason: 'inconsistent-state repair and expiry must both finish');
    expect(timers, hasLength(3), reason: 'repeated start must not duplicate capture timers');
    await sync.stop();
  });
  test('admission keeps distinct memory WALs with colliding derived names', () async {
    final old = await seedOldRow();
    final entered = Completer<void>();
    final release = Completer<void>();
    final sync = LocalWalSyncImpl(_Listener(),
        freeDiskBytes: () async => 64 << 30,
        deltaIndexAllowed: () async => true,
        loadWals: () async {
          final rows = await WalFileManager.loadWals();
          entered.complete();
          await release.future;
          return rows;
        });
    sync.start();
    await entered.future;
    final pending = [
      for (final payload in [
        [4, 5],
        [6, 7]
      ])
        Wal(
            timerStart: 2,
            codec: BleAudioCodec.opus,
            seconds: 1,
            storage: WalStorage.mem,
            ownerUid: 'owner-a',
            totalFrames: 1,
            data: [payload])
    ];
    sync.testWals = pending;
    release.complete();
    await sync.walReady;
    await sync.stop();
    (await sync.indexWorkerForTesting)?.close();
    final rows = await WalFileManager.loadIndexedWals();
    expect(rows, hasLength(3));
    expect(rows.map((w) => w.filePath).toSet(), hasLength(3));
    for (var i = 0; i < pending.length; i++) {
      expect(await File('${documents.path}/${pending[i].filePath}').readAsBytes(), [2, 0, 0, 0, 4 + 2 * i, 5 + 2 * i]);
    }
    expect(rows.map((w) => w.filePath), contains(old.filePath));
  });

  test('transcript confirmation fails closed when admission prevents its index save', () async {
    await seedOldRow();
    final originalIndex = await File('${documents.path}/wals.json').readAsString();
    final sync = LocalWalSyncImpl(_Listener(), loadWals: () async => throw StateError('load unavailable'));
    sync.start();
    await pumpEventQueue(times: 30);
    final pending = Wal(
        timerStart: 470,
        codec: BleAudioCodec.opus,
        seconds: 30,
        storage: WalStorage.mem,
        status: WalStatus.miss,
        ownerUid: 'owner-a',
        conversationId: 'c1',
        data: [
          [7, 8]
        ]);
    sync.testWals = [pending];
    try {
      await expectLater(
          sync.confirmSessionTranscription(500, 'c1', transcriptSpans: [(469, 531)]), throwsA(isA<StateError>()));
      expect(pending.status, WalStatus.miss);
      expect(pending.syncedAt, 0);
      expect(pending.keptForTranscriptRecovery, isTrue);
      expect(await File('${documents.path}/wals.json').readAsString(), originalIndex);
    } finally {
      await sync.stop();
    }
  });
}
