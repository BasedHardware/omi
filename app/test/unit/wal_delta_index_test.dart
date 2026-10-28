import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/wals/sync_job_poller.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/experiments/wal_delta_index_gate.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_index_inventory.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/off_ui_isolate.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:omi/utils/wal_index_worker.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _CountedWal extends Wal {
  _CountedWal(int start)
      : super(
            timerStart: start,
            codec: BleAudioCodec.opus,
            seconds: 30,
            storage: WalStorage.disk,
            status: WalStatus.synced,
            filePath: 'audio_$start.bin');
  int statusReads = 0;
  @override
  WalStatus get status {
    statusReads++;
    return super.status;
  }

  int serializations = 0;
  int fingerprints = 0;
  @override
  Map<String, dynamic> toJson() {
    serializations++;
    return super.toJson();
  }

  @override
  int get persistentFingerprint {
    fingerprints++;
    return super.persistentFingerprint;
  }
}

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    dir = await Directory.systemTemp.createTemp('wal_delta_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (_) async => dir.path);
    await WalFileManager.init();
  });
  tearDown(() async {
    WalFileManager.quarantineRenameForTesting = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await dir.delete(recursive: true);
  });

  test('70k history: one mutation serializes one identity and never fingerprints history', () {
    final inventory = WalIndexInventory();
    final rows = List.generate(70000, _CountedWal.new);
    final active = inventory.track(rows);
    final retired = inventory.track([]);
    final foreign = inventory.track([]);
    expect(inventory.takeDelta().changed, hasLength(70000));
    for (final row in rows) {
      row.serializations = 0;
    }

    rows[42000].retryCount++;
    final delta = inventory.takeDelta();
    expect(delta.changed, hasLength(1));
    expect(delta.changed.values.single['retry_count'], 1);
    expect(rows.fold<int>(0, (sum, w) => sum + w.serializations), 1);
    expect(rows.fold<int>(0, (sum, w) => sum + w.fingerprints), 0);
    expect(inventory.takeDelta().isEmpty, isTrue);

    // Logout and load parking preserve both identities; moves never delete audio.
    retired.add(active.removeAt(3));
    foreign.add(active.removeAt(5));
    final moved = inventory.takeDelta();
    expect(moved.removed, isEmpty);
    expect(moved.changed, hasLength(2));
    active.removeAt(10);
    expect(inventory.takeDelta().removed, hasLength(1));
  });

  test('reconciliation does not visit 70k synced rows when polling one uploaded job', () async {
    final now = DateTime(2026, 10, 28);
    SyncRateLimiter.instance.clear();
    final history = List.generate(70000, _CountedWal.new);
    final job = Wal(
        timerStart: 80000,
        codec: BleAudioCodec.opus,
        seconds: 30,
        storage: WalStorage.disk,
        status: WalStatus.uploaded,
        jobId: 'pending',
        jobPendingConfirmedAt: now.millisecondsSinceEpoch ~/ 1000);
    var calls = 0;
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        jobPoller: SyncJobPoller(clock: () => now),
        persistWals: (_) async {},
        jobStatusFetcher: (id) async {
          calls++;
          return SyncJobFetch(SyncJobFetchOutcome.ok, SyncJobStatusResponse(jobId: id, status: 'processing'));
        });
    sync.testWals = [...history, job];
    for (final row in history) {
      row.statusReads = 0;
    }
    await sync.reconcileUploadedWals();
    expect(calls, 1);
    expect(sync.hasUploadedWals, isTrue);
    expect(history.fold<int>(0, (sum, w) => sum + w.statusReads), 0);
    sync.testWals.remove(job);
    sync.testForeignWals.add(job);
    expect(sync.hasUploadedWals, isFalse, reason: 'the scheduler never wakes for another account');
  });

  test('failed delta retry retains removals and the latest in-flight mutation', () {
    final inventory = WalIndexInventory();
    final a = _CountedWal(1), b = _CountedWal(2);
    final rows = inventory.track([a, b]);
    final first = inventory.takeDelta();
    a.retryCount = 4;
    rows.remove(b);
    inventory.retry(first);
    final retry = inventory.takeDelta();
    expect(retry.changed.values.single['retry_count'], 4);
    expect(retry.removed, hasLength(1));
    a.isSyncing = true;
    a.deviceDownloadFraction = 0.5;
    expect(inventory.takeDelta().isEmpty, isTrue, reason: 'runtime progress does not cause disk writes');
  });

  test('old 70k index loads off-isolate; delta worker keeps version 1 and all custody buckets', () async {
    final rows = List.generate(70000, (i) => _CountedWal(i)..ownerUid = i % 3 == 0 ? 'foreign' : 'current');
    final file = File('${dir.path}/wals.json');
    await file.writeAsString(jsonEncode({'version': 1, 'wals': rows.map((w) => w.toJson()).toList()}));
    offUiIsolateWorkerCompletions = 0;
    offUiIsolateFallbacks = 0;
    final loaded = await WalFileManager.loadWals();
    expect(loaded, hasLength(70000));
    expect(offUiIsolateWorkerCompletions, greaterThan(0));
    expect(offUiIsolateFallbacks, 0, reason: 'decode + Wal construction must run on a worker');

    final inventory = WalIndexInventory()..primeLoaded(loaded);
    final retired = inventory.track(loaded.take(100));
    final foreign = inventory.track(loaded.skip(100).where((w) => w.ownerUid == 'foreign'));
    final current = inventory.track(loaded.skip(100).where((w) => w.ownerUid != 'foreign'));
    final worker = await WalIndexWorker.start(file.path, seedFromDisk: true);
    addTearDown(worker.close);
    var delta = inventory.takeDelta();
    expect(delta.isEmpty, isTrue, reason: 'loading never serializes or sends the unchanged history back to the worker');
    await worker.apply(delta.changed, delta.removed);
    current[4].status = WalStatus.miss;
    current[4].retryCount = 2;
    delta = inventory.takeDelta();
    expect(delta.changed, hasLength(1));
    await worker.apply(delta.changed, delta.removed);

    final saved = jsonDecode(await file.readAsString()) as Map<String, dynamic>;
    expect(saved['version'], 1, reason: 'released clients read the exact same schema');
    final reloaded = await WalFileManager.loadWals();
    expect(reloaded, hasLength(70000));
    expect(reloaded.map((w) => w.timerStart).toSet().containsAll(loaded.map((w) => w.timerStart)), isTrue);
    expect(reloaded.where((w) => w.ownerUid == 'foreign').length, loaded.where((w) => w.ownerUid == 'foreign').length);
    expect(reloaded.where((w) => w.status == WalStatus.synced), hasLength(69999));
    expect(retired, hasLength(100));
    expect(foreign, isNotEmpty);
    final backup = jsonDecode(await File('${dir.path}/wals_backup.json').readAsString()) as Map<String, dynamic>;
    expect((backup['wals'] as List).where((w) => w['status'] == 'synced'), hasLength(70000));
    // This is a large file compatibility fixture, not an elapsed-time gate.
  }, timeout: const Timeout(Duration(minutes: 2)));

  test('a memory row persisted later retains its admission order across restart', () async {
    final inventory = WalIndexInventory();
    final first = _CountedWal(1)..storage = WalStorage.mem;
    final second = _CountedWal(2);
    inventory.track([first, second]);
    final worker = await WalIndexWorker.start('${dir.path}/wals.json');
    addTearDown(worker.close);
    Future<void> save() async {
      final delta = inventory.takeDelta();
      await worker.apply(delta.changed, delta.removed);
    }

    await save();
    expect((await WalFileManager.loadWals()).map((w) => w.timerStart), [2]);
    first.storage = WalStorage.disk;
    await save();
    expect((await WalFileManager.loadWals()).map((w) => w.timerStart), [1, 2]);
    first.storage = WalStorage.mem;
    await save();
    first.storage = WalStorage.disk;
    await save();
    expect((await WalFileManager.loadWals()).map((w) => w.timerStart), [1, 2]);
  });

  test('worker failure cannot acknowledge disk, and retry is complete', () async {
    final file = File('${dir.path}/wals.json');
    final worker = await WalIndexWorker.start(file.path);
    addTearDown(worker.close);
    Directory('${file.path}.tmp').createSync();
    await expectLater(worker.apply({1: _CountedWal(1).toJson()}, []), throwsA(isA<FileSystemException>()));
    expect(await file.exists(), isFalse);
    await Directory('${file.path}.tmp').delete();
    await worker.apply({2: _CountedWal(2).toJson()}, []);
    expect((await WalFileManager.loadWals()).map((w) => w.timerStart), [1, 2]);
  });

  test('LocalWalSync production path sends only the changed record after initial admission', () async {
    final rows = List.generate(1000, _CountedWal.new);
    final sync = LocalWalSyncImpl(_Listener());
    sync.testWals = rows;
    await sync.persistRetryMetadata(rows.first);
    final before = await sync.getAllWals();
    for (final row in rows) {
      row.serializations = 0;
    }
    rows.last.retryCount = 3;
    await sync.persistRetryMetadata(rows.last);
    expect(identical(await sync.getAllWals(), before), isTrue,
        reason: 'status updates reuse the published membership snapshot');
    expect(rows.fold<int>(0, (sum, w) => sum + w.serializations), 1);
    expect(rows.fold<int>(0, (sum, w) => sum + w.fingerprints), 0);
    expect((await WalFileManager.loadWals()).singleWhere((w) => w.timerStart == rows.last.timerStart).retryCount, 3);
    await sync.stop();
  });

  test('kill switch saves full snapshots through the legacy writer and never starts a worker', () async {
    final rows = List.generate(50, _CountedWal.new);
    final sync = LocalWalSyncImpl(_Listener(), deltaIndexAllowed: () async => false);
    sync.testWals = rows;
    rows.last.retryCount = 2;
    await sync.persistRetryMetadata(rows.last);
    expect(sync.indexWorkerForTesting, isNull);
    final onDisk = await WalFileManager.loadWals();
    expect(onDisk, hasLength(50));
    expect(onDisk.singleWhere((w) => w.timerStart == rows.last.timerStart).retryCount, 2);
    await sync.stop();
  });

  group('WalDeltaIndexGate', () {
    test('only an explicit true turns the delta writer off', () async {
      expect(await WalDeltaIndexGate.deltaWriterAllowed(readFlag: (_) async => true), isFalse);
      expect(await WalDeltaIndexGate.deltaWriterAllowed(readFlag: (_) async => false), isTrue);
      expect(await WalDeltaIndexGate.deltaWriterAllowed(readFlag: (_) async => throw StateError('offline')), isTrue);
    });
  });

  test('worker exit fails every pending request instead of wedging saves', () async {
    final beforeWrite = ReceivePort();
    addTearDown(beforeWrite.close);
    final entered = Completer<void>();
    beforeWrite.listen((_) => entered.complete());
    final worker = await WalIndexWorker.start('${dir.path}/wals.json', beforeWriteForTesting: beforeWrite.sendPort);
    addTearDown(worker.close);
    final first = worker.apply({0: _CountedWal(1).toJson()}, []);
    final second = worker.apply({1: _CountedWal(2).toJson()}, []);
    final firstFailed = expectLater(first, throwsA(isA<FileSystemException>()));
    final secondFailed = expectLater(second, throwsA(isA<FileSystemException>()));
    await entered.future;
    worker.close(); // Real VM isolate termination, while a write is admitted.
    await Future.wait([firstFailed, secondFailed]).timeout(const Duration(seconds: 5));
    expect(worker.isDead, isTrue);
    expect(File('${dir.path}/wals.json').existsSync(), isFalse, reason: 'no false durable acknowledgement');
    await expectLater(worker.apply({}, []), throwsA(isA<FileSystemException>()));
  });

  test('LocalWalSync replaces a dead worker using current tokens and all custody buckets', () async {
    final a = _CountedWal(1), removed = _CountedWal(2), b = _CountedWal(3);
    final retired = _CountedWal(4)..ownerUid = 'retired';
    final foreign = _CountedWal(5)..ownerUid = 'foreign';
    final discardedForeign = _CountedWal(8)..ownerUid = 'foreign';
    final memory = _CountedWal(6)..storage = WalStorage.mem;
    final sync = LocalWalSyncImpl(_Listener());
    sync.testWals = [a, removed, b, memory];
    sync.testRetiredWals.add(retired);
    sync.testForeignWals.addAll([foreign, discardedForeign]);
    await sync.persistRetryMetadata(a);
    sync.testWals.remove(removed); // Disk compacts; main tokens retain the gap.
    await sync.persistRetryMetadata(a);
    final dead = (await sync.indexWorkerForTesting)!;
    addTearDown(dead.close);
    dead.close();
    b.retryCount = 7;
    await expectLater(
        sync.persistRetryMetadata(b).timeout(const Duration(seconds: 5)), throwsA(isA<FileSystemException>()));
    expect(sync.indexWorkerForTesting, isNull);
    // Mutations and removals arriving after the failed write must also survive.
    a.retryCount = 9;
    sync.testForeignWals.remove(discardedForeign);
    final added = _CountedWal(7);
    sync.testWals.add(added);
    await sync.persistRetryMetadata(added);
    final replacement = (await sync.indexWorkerForTesting)!;
    addTearDown(replacement.close);
    final loaded = await WalFileManager.loadWals();
    expect(loaded.map((w) => w.timerStart), [1, 3, 4, 5, 7]);
    expect(loaded.map((w) => w.retryCount), [9, 7, 0, 0, 0]);
    expect(loaded.singleWhere((w) => w.timerStart == 4).ownerUid, 'retired');
    expect(loaded.singleWhere((w) => w.timerStart == 5).ownerUid, 'foreign');
    // Subsequent deltas still address the same tokens, not compacted disk ordinals.
    b.retryCount = 8;
    await sync.persistRetryMetadata(b);
    expect((await WalFileManager.loadWals()).map((w) => (w.timerStart, w.retryCount)),
        [(1, 9), (3, 8), (4, 0), (5, 0), (7, 0)]);
  });

  test('a replacement whose disk write fails still applies removals on its next retry', () async {
    final a = _CountedWal(1), b = _CountedWal(2);
    final sync = LocalWalSyncImpl(_Listener());
    sync.testWals = [a, b];
    await sync.persistRetryMetadata(a);
    final dead = (await sync.indexWorkerForTesting)!;
    addTearDown(dead.close);
    dead.close();
    a.retryCount = 1;
    await expectLater(sync.persistRetryMetadata(a), throwsA(isA<FileSystemException>()));
    final blockedTmp = Directory('${dir.path}/wals.json.tmp');
    await blockedTmp.create();
    await expectLater(sync.persistRetryMetadata(a), throwsA(isA<FileSystemException>()));
    final replacement = (await sync.indexWorkerForTesting)!;
    addTearDown(replacement.close);
    expect(replacement.isDead, isFalse);
    expect((await WalFileManager.loadWals()).map((w) => w.retryCount), [0, 0], reason: 'failed write was not durable');
    sync.testWals.remove(b);
    a.retryCount = 2;
    await blockedTmp.delete();
    await sync.persistRetryMetadata(a);
    expect((await WalFileManager.loadWals()).map((w) => (w.timerStart, w.retryCount)), [(1, 2)]);
  });

  test('backup seed survives an unreadable main that cannot be quarantined', () async {
    final file = File('${dir.path}/wals.json');
    await file.writeAsString('{unreadable');
    final backup = File('${dir.path}/wals_backup.json');
    await backup.writeAsString(jsonEncode({
      'version': 1,
      'wals': [_CountedWal(1).toJson(), _CountedWal(2).toJson()]
    }));
    WalFileManager.quarantineRenameForTesting = (_) async => throw const FileSystemException('rename denied');
    final sync = LocalWalSyncImpl(_Listener());
    await sync.loadForOnDeviceWorker();
    expect(sync.testWals, hasLength(2));
    expect(sync.testWals.first.loadedIndexSource, backup.path);
    sync.testWals.last.retryCount = 3;
    await sync.persistRetryMetadata(sync.testWals.last);
    addTearDown((await sync.indexWorkerForTesting)!.close);
    expect((await WalFileManager.loadWals()).map((w) => (w.timerStart, w.retryCount)), [(1, 0), (2, 3)]);
    expect(jsonDecode(await backup.readAsString())['wals'], hasLength(2), reason: 'corrupt main never replaces backup');
  });

  test('an unseedable startup fails closed and retries from admitted rows in-session', () async {
    final file = File('${dir.path}/wals.json');
    await file.writeAsString(jsonEncode({
      'version': 1,
      'wals': [_CountedWal(1).toJson(), _CountedWal(2).toJson()]
    }));
    final sync = LocalWalSyncImpl(_Listener());
    await sync.loadForOnDeviceWorker();
    await file.delete(); // The validated source becomes unavailable before spawn.
    final added = _CountedWal(3);
    sync.testWals.add(added);
    await expectLater(
        sync.persistRetryMetadata(added).timeout(const Duration(seconds: 5)), throwsA(isA<FileSystemException>()));
    expect(sync.indexWorkerForTesting, isNull);
    expect(await file.exists(), isFalse);
    sync.testWals.first.retryCount = 6;
    await sync.persistRetryMetadata(added);
    addTearDown((await sync.indexWorkerForTesting)!.close);
    expect((await WalFileManager.loadWals()).map((w) => (w.timerStart, w.retryCount)), [(1, 6), (2, 0), (3, 0)]);
  });

  test('load-time invalid-entry repair and live worker share writer serialization', () async {
    final file = File('${dir.path}/wals.json');
    await file.writeAsString(jsonEncode({
      'version': 1,
      'wals': [_CountedWal(1).toJson(), _CountedWal(2).toJson()]
    }));
    final beforeWrite = ReceivePort();
    addTearDown(beforeWrite.close);
    var workerEntered = false;
    beforeWrite.listen((resume) {
      workerEntered = true;
      (resume as SendPort).send(null);
    });
    final worker =
        await WalFileManager.createIndexWorker(seedFromDisk: true, beforeWriteForTesting: beforeWrite.sendPort);
    addTearDown(worker.close);
    // External damage after the worker was seeded: load keeps readable entries.
    await file.writeAsString(jsonEncode({
      'version': 1,
      'wals': [
        _CountedWal(1).toJson(),
        {'broken': true}
      ]
    }));
    final quarantineEntered = Completer<void>();
    final releaseQuarantine = Completer<void>();
    WalFileManager.quarantineRenameForTesting = (source) async {
      await source.rename('${source.path}.corrupt-test');
      quarantineEntered.complete();
      await releaseQuarantine.future;
    };
    final load = WalFileManager.loadWals();
    await quarantineEntered.future;
    final write = worker.apply({1: (_CountedWal(2)..retryCount = 5).toJson(), 2: _CountedWal(3).toJson()}, []);
    await pumpEventQueue();
    expect(workerEntered, isFalse, reason: 'no worker tmp/rename while load holds the repair lock');
    releaseQuarantine.complete();
    expect((await load).map((w) => w.timerStart), [1]);
    await write;
    expect(workerEntered, isTrue);
    expect((await WalFileManager.loadWals()).map((w) => (w.timerStart, w.retryCount)), [(1, 0), (2, 5), (3, 0)]);
    expect(await File('${file.path}.tmp').exists(), isFalse);
    final backup = jsonDecode(await File('${dir.path}/wals_backup.json').readAsString());
    expect((backup['wals'] as List).map((w) => w['timer_start']), [1]);
  });
}
