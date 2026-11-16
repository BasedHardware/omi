import 'dart:io';
import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_write_intent.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _UnwritableArchive implements File {
  @override
  Future<File> writeAsBytes(List<int> bytes, {FileMode mode = FileMode.write, bool flush = false}) =>
      throw const FileSystemException('archive write denied');
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _InterruptedLedger extends LocalWalSyncImpl {
  _InterruptedLedger() : super(_Listener(), freeDiskBytes: () async => 64 << 30);
  @override
  Future<void> addExternalWal(Wal wal, {required int admittedGeneration}) async {
    throw StateError('interrupted before row registration');
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory documents;
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'owner-a'});
    await SharedPreferencesUtil.init();
    documents = await Directory.systemTemp.createTemp('wal_orphan_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (_) async => documents.path);
    await WalFileManager.init();
  });
  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await documents.delete(recursive: true);
  });

  LocalWalSyncImpl failingLedger() => LocalWalSyncImpl(_Listener(),
      freeDiskBytes: () async => 64 << 30,
      persistWals: (_) async => throw const FileSystemException('injected index failure'));

  Future<void> expectRestartRetainsFile(Wal original) async {
    final restarted = LocalWalSyncImpl(_Listener());
    await restarted.loadForOnDeviceWorker();
    final recovered = restarted.testWals.single;
    expect(recovered.filePath, original.filePath);
    expect(recovered.ownerUid, 'owner-a');
    expect(recovered.timerStart, original.timerStart);
    expect(recovered.totalFrames, original.totalFrames);
    expect(await File('${documents.path}/${recovered.filePath}').exists(), isTrue);
    // Discovery is not index durability and must never authorize device ACK.
    expect(await restarted.hasDurableWal(recovered, admittedGeneration: restarted.sessionGeneration), isFalse);
  }

  test('live fsync followed by failed index save survives a fresh ledger', () async {
    final sync = failingLedger();
    final live = Wal(
        timerStart: 1794741663,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.mem,
        device: 'pendant',
        ownerUid: 'owner-a',
        totalFrames: 2,
        data: [
          [1, 2],
          [3, 4]
        ]);
    sync.testWals = [live];
    await expectLater(sync.stop(), throwsA(isA<FileSystemException>()));
    expect(live.storage, WalStorage.disk);
    await expectRestartRetainsFile(live);
  });

  test('device chunk fsync followed by failed index save survives a fresh ledger', () async {
    final sync = failingLedger();
    await expectLater(
        sync.persistDeviceChunk(
            source: Wal(timerStart: 1794741663, codec: BleAudioCodec.opus, seconds: 10, device: 'pendant'),
            frames: [
              [1, 2],
              [3, 4]
            ],
            timerStart: 1794741663,
            admittedGeneration: sync.sessionGeneration,
            nextCollisionSequence: () => 1),
        throwsA(isA<FileSystemException>()));
    await expectRestartRetainsFile(sync.testWals.single);
  });
  test('failed quarantine rename preserves rejected row references before repair overwrites the index', () async {
    final audio = File('${documents.path}/audio_rejected.bin');
    await audio.writeAsBytes([1, 2, 3]);
    final valid = Wal(timerStart: 1, codec: BleAudioCodec.opus, storage: WalStorage.disk, seconds: 10);
    final rejected = {...valid.toJson(), 'file_path': 'audio_rejected.bin', 'timer_start': 'invalid'};
    final original = jsonEncode({
      'version': 1,
      'wals': [valid.toJson(), rejected]
    });
    await File('${documents.path}/wals.json').writeAsString(original);
    WalFileManager.quarantineRenameForTesting = (_) async => throw const FileSystemException('rename denied');
    addTearDown(() => WalFileManager.quarantineRenameForTesting = null);
    final loaded = await WalFileManager.loadWals();
    expect(loaded, hasLength(1));
    await WalFileManager.saveWals(loaded);
    await WalFileManager.saveWals(loaded);
    final retired = await documents.list().where((f) => f.path.contains('wals.json.corrupt-')).toList();
    expect(retired, hasLength(1), reason: 'rejecting a row must durably retire its file reference');
    expect(await File(retired.single.path).readAsString(), original);
    expect(await audio.readAsBytes(), [1, 2, 3]);
  });

  test('recovery commits once, retires its intent, and a user delete never resurrects it', () async {
    final failed = failingLedger();
    failed.testWals = [
      Wal(
          timerStart: 1,
          codec: BleAudioCodec.opus,
          seconds: 10,
          device: 'pendant',
          ownerUid: 'owner-a',
          totalFrames: 1,
          data: [
            [1, 2]
          ])
    ];
    await expectLater(failed.stop(), throwsA(isA<FileSystemException>()));
    final sync = LocalWalSyncImpl(_Listener(), deltaIndexAllowed: () async => true);
    await sync.loadForOnDeviceWorker();
    final wal = sync.testWals.single;
    await sync.persistRetryMetadata(wal);
    addTearDown((await sync.indexWorkerForTesting)!.close);
    expect(await sync.hasDurableWal(wal, admittedGeneration: sync.sessionGeneration), isTrue);
    expect(await WalWriteIntent.exists(documents, wal.filePath!), isFalse);
    expect(await WalFileManager.loadWals(), hasLength(1));
    await sync.deleteWal(wal);
    expect(await File('${documents.path}/${wal.filePath}').exists(), isFalse);
    expect(await WalFileManager.loadWals(), isEmpty);
  });

  test('a complete intent with a foreign owner stays parked through replay', () async {
    final failed = failingLedger();
    failed.testWals = [
      Wal(
          timerStart: 1,
          codec: BleAudioCodec.opus,
          seconds: 10,
          device: 'pendant',
          ownerUid: 'foreign-owner',
          totalFrames: 1,
          data: [
            [1, 2]
          ])
    ];
    await expectLater(failed.stop(), throwsA(isA<FileSystemException>()));
    final sync = LocalWalSyncImpl(_Listener());
    await sync.loadForOnDeviceWorker();
    expect(sync.testWals, isEmpty);
    expect(sync.testForeignWals.single.ownerUid, 'foreign-owner');
    expect(await sync.hasDurableWal(sync.testForeignWals.single, admittedGeneration: sync.sessionGeneration), isFalse);
  });

  test('partial, mismatched and malformed intents retain bytes without publishing rows', () async {
    final wal = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        totalFrames: 1,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_partial.bin');
    await WalWriteIntent.write(documents, wal, [1, 2, 3]);
    final file = File('${documents.path}/${wal.filePath}');
    for (final bytes in [
      [1, 2],
      [1, 2, 4]
    ]) {
      await file.writeAsBytes(bytes);
      expect(await WalFileManager.loadWals(), isEmpty);
      expect(await file.readAsBytes(), bytes);
      expect(await WalWriteIntent.exists(documents, wal.filePath!), isTrue);
    }
    final marker = File('${documents.path}/.wal-pending/${wal.filePath}.json');
    await marker.writeAsString('{torn metadata');
    expect(await WalFileManager.loadWals(), isEmpty);
    expect(await marker.readAsString(), '{torn metadata');
    // An old audio file without a new intent is never adopted or removed.
    final old = File('${documents.path}/audio_historical.bin');
    await old.writeAsBytes([9, 9]);
    expect(await WalFileManager.loadWals(), isEmpty);
    expect(await old.readAsBytes(), [9, 9]);
  });

  test('crash after main index commit retires the leftover intent without duplicating its row', () async {
    final wal = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        totalFrames: 1,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_committed.bin');
    await WalWriteIntent.write(documents, wal, [1, 2, 3]);
    await WalFileManager.saveWals([wal]);
    expect(await WalFileManager.loadWals(), hasLength(1));
    expect(await WalWriteIntent.exists(documents, wal.filePath!), isFalse);
    expect(await WalFileManager.loadWals(), hasLength(1));
  });

  test('unknown disk storage is retired instead of becoming an empty memory WAL', () async {
    final wal = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_unknown_storage.bin');
    await File('${documents.path}/${wal.filePath}').writeAsBytes([1, 2, 3]);
    await File('${documents.path}/wals.json').writeAsString(jsonEncode({
      'version': 1,
      'wals': [
        {...wal.toJson(), 'storage': 'future-storage'}
      ]
    }));
    expect(await WalFileManager.loadWals(), isEmpty,
        reason: 'unknown storage must not silently default to mem and replace its file on flush');
    expect(await File('${documents.path}/${wal.filePath}').readAsBytes(), [1, 2, 3]);
    expect(await documents.list().where((f) => f.path.contains('wals.json.corrupt-')).length, 1);
  });

  test('account cleanup cannot clear references left after owner-scoped file deletion', () async {
    final remaining = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'other-account',
        filePath: 'audio_other_owner.bin');
    await File('${documents.path}/${remaining.filePath}').writeAsBytes([1, 2, 3]);
    await WalFileManager.saveWals([remaining]);
    await WalFileManager.clearAll();
    expect((await WalFileManager.loadWals()).single.filePath, remaining.filePath,
        reason: 'purge may leave other owners or failed deletes; their rows must survive');
  });
  test('device write interrupted before registration keeps a replayable row and collision name', () async {
    final interrupted = _InterruptedLedger();
    final source = Wal(timerStart: 1794741663, codec: BleAudioCodec.opus, seconds: 10, device: 'pendant');
    await expectLater(
        interrupted.persistDeviceChunk(
            source: source,
            frames: [
              [1, 2]
            ],
            timerStart: source.timerStart,
            admittedGeneration: 0,
            nextCollisionSequence: () => 1),
        throwsStateError);
    expect(interrupted.testWals, isEmpty);
    final row = (await WalFileManager.loadWals()).single;
    expect(row.ownerUid, 'owner-a');
    expect(row.totalFrames, 1);
    expect(row.storage, WalStorage.disk);
    final firstBytes = await File('${documents.path}/${row.filePath}').readAsBytes();
    await expectLater(
        interrupted.persistDeviceChunk(
            source: source,
            frames: [
              [3, 4]
            ],
            timerStart: source.timerStart,
            admittedGeneration: 0,
            nextCollisionSequence: () => 1),
        throwsStateError);
    expect(await WalFileManager.loadWals(), hasLength(2));
    expect(await File('${documents.path}/${row.filePath}').readAsBytes(), firstBytes);
  });

  test('empty-ring marker interrupted before registration replays its exact range without ACK authority', () async {
    final interrupted = _InterruptedLedger();
    await expectLater(
        interrupted.persistEmptyRingRecords(
            source: Wal(timerStart: 1, codec: BleAudioCodec.opus, seconds: 0, device: 'pendant'),
            ringId: 17,
            start: 41,
            end: 42,
            admittedGeneration: 0),
        throwsStateError);
    final restarted = LocalWalSyncImpl(_Listener());
    await restarted.loadForOnDeviceWorker();
    final row = restarted.testWals.single;
    expect((row.downloadRingId, row.downloadSeqStart, row.downloadSeqEnd), (17, 41, 42));
    expect(await restarted.hasDurableWal(row, admittedGeneration: 0), isFalse);
  });

  test('intent replay plus existing disk tokens preserves both rows on delta commit', () async {
    final existing = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_existing.bin');
    final pending = Wal(
        timerStart: 2,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_pending.bin');
    await File('${documents.path}/${existing.filePath}').writeAsBytes([5, 6]);
    await WalFileManager.saveWals([existing]);
    await WalWriteIntent.write(documents, pending, [1, 2, 3]);
    final restarted = LocalWalSyncImpl(_Listener(), deltaIndexAllowed: () async => true);
    await restarted.loadForOnDeviceWorker();
    expect(restarted.testWals, hasLength(2));
    await restarted.persistRetryMetadata(restarted.testWals.last);
    addTearDown((await restarted.indexWorkerForTesting)!.close);
    expect(
        (await WalFileManager.loadIndexedWals()).map((w) => w.filePath), ['audio_existing.bin', 'audio_pending.bin']);
    expect(await WalWriteIntent.exists(documents, pending.filePath!), isFalse);
  });
  test('a failed quarantine copy refuses repair and leaves both index sources unchanged', () async {
    final original = jsonEncode({
      'version': 1,
      'wals': [
        {'file_path': 'audio_only_copy.bin'}
      ]
    });
    final main = File('${documents.path}/wals.json');
    await main.writeAsString(original);
    final backup = File('${documents.path}/wals_backup.json');
    await backup.writeAsString('backup evidence');
    WalFileManager.quarantineRenameForTesting = (_) async => throw const FileSystemException('rename denied');
    addTearDown(() => WalFileManager.quarantineRenameForTesting = null);
    await IOOverrides.runZoned(() async {
      await expectLater(WalFileManager.loadWals(), throwsA(isA<FileSystemException>()));
    }, createFile: (path) {
      if (path.contains('wals.json.corrupt-')) return _UnwritableArchive();
      return Zone.root.run(() => File(path));
    });
    expect(await main.readAsString(), original);
    expect(await backup.readAsString(), 'backup evidence');
  });
  test('a flush racing startup cannot seed an empty worker and forget loaded files', () async {
    final old = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_before_startup.bin');
    await File('${documents.path}/${old.filePath}').writeAsBytes([1, 2, 3]);
    await WalFileManager.saveWals([old]);
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
    // Give the real worker time to start if startup incorrectly permits a save.
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
    addTearDown((await sync.indexWorkerForTesting)!.close);
    expect((await WalFileManager.loadIndexedWals()).map((w) => w.filePath), [old.filePath, added.filePath],
        reason: 'later deltas must retain files loaded at startup');
  });
  test('an intent missing its captured owner cannot become the next account audio', () async {
    final wal = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_unknown_owner.bin');
    await WalWriteIntent.write(documents, wal, [1, 2, 3]);
    final intent = File('${documents.path}/.wal-pending/${wal.filePath}.json');
    final metadata = jsonDecode(await intent.readAsString());
    (metadata['wal'] as Map).remove('owner_uid');
    await intent.writeAsString(jsonEncode(metadata));
    expect(await WalFileManager.loadWals(), isEmpty);
    expect(await intent.exists(), isTrue);
    expect(await File('${documents.path}/${wal.filePath}').readAsBytes(), [1, 2, 3]);
  });
}
