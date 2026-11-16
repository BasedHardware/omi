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

class _UndeletableAudio implements File {
  final File real;
  _UndeletableAudio(this.real);
  @override
  Directory get parent => real.parent;
  @override
  String get path => real.path;
  @override
  Future<bool> exists() => real.exists();
  @override
  Future<File> delete({bool recursive = false}) => throw const FileSystemException('audio delete denied');
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _CreationBarrierFile implements File {
  final File real;
  final Completer<void> entered, release;
  _CreationBarrierFile(this.real, this.entered, this.release);
  @override
  Directory get parent => real.parent;
  @override
  Future<bool> exists() => real.exists();
  @override
  String get path => real.path;
  @override
  Future<File> create({bool recursive = false, bool exclusive = false}) async {
    if (!entered.isCompleted) entered.complete();
    await release.future;
    return real.create(recursive: recursive, exclusive: exclusive);
  }

  @override
  Future<File> writeAsBytes(List<int> bytes, {FileMode mode = FileMode.write, bool flush = false}) =>
      real.writeAsBytes(bytes, mode: mode, flush: flush);
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
    WalFileManager.beforeLegacyMigrationSaveForTesting = null;
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
  test('failed audio deletion keeps its only durable write intent for restart', () async {
    final sync = failingLedger();
    sync.testWals = [
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
    await expectLater(sync.stop(), throwsA(isA<FileSystemException>()));
    final wal = sync.testWals.single;
    final name = wal.filePath!;
    expect(await File('${documents.path}/$name').exists(), isTrue);
    await IOOverrides.runZoned(() => sync.deleteWal(wal),
        createFile: (path) {
          final real = Zone.root.run(() => File(path));
          return path.endsWith('/$name') ? _UndeletableAudio(real) : real;
        },
        fseGetType: (path, followLinks) => Zone.root.run(() => FileSystemEntity.type(path, followLinks: followLinks)));
    expect(await WalWriteIntent.exists(documents, name), isTrue);
    await expectRestartRetainsFile(wal);
  });

  test('intent retirement failure after audio deletion retains the row and retries on a missing file', () async {
    final sync = failingLedger();
    sync.testWals = [
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
    await expectLater(sync.stop(), throwsA(isA<FileSystemException>()));
    final wal = sync.testWals.single;
    final name = wal.filePath!;
    await IOOverrides.runZoned(() => sync.deleteWal(wal),
        createFile: (path) {
          final real = Zone.root.run(() => File(path));
          return path.endsWith('/.wal-pending/$name.json') ? _UndeletableAudio(real) : real;
        },
        fseGetType: (path, followLinks) => Zone.root.run(() => FileSystemEntity.type(path, followLinks: followLinks)));
    expect(sync.testWals, hasLength(1));
    expect(await File('${documents.path}/$name').exists(), isFalse);
    expect(await WalWriteIntent.exists(documents, name), isTrue);
    expect(await WalFileManager.loadWals(), isEmpty, reason: 'a missing file cannot be resurrected by an intent');
    // The retry retires the intent before removing its row, without deleting audio twice.
    await expectLater(sync.deleteWal(wal), throwsA(isA<FileSystemException>()));
    expect(sync.testWals, isEmpty);
    expect(await WalWriteIntent.exists(documents, name), isFalse);
  });
  test('a stale index cleanup cannot retire a newer transaction reusing its filename', () async {
    final old = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_reused.bin');
    await WalWriteIntent.write(documents, old, [1, 2]);
    await File('${documents.path}/${old.filePath}').delete();
    await WalWriteIntent.retireFile(documents, old.filePath!);
    final replacement = Wal.fromJson(old.toJson());
    await WalWriteIntent.write(documents, replacement, [3, 4]);
    await WalWriteIntent.retire(documents, old);
    expect(await WalWriteIntent.exists(documents, replacement.filePath!), isTrue);
    expect((await WalFileManager.loadWals()).single.filePath, replacement.filePath);
  });

  test('a stale main row cannot retire the intent of replacement bytes at the same filename', () async {
    final old = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        totalFrames: 1,
        storage: WalStorage.disk,
        status: WalStatus.synced,
        ownerUid: 'owner-a',
        filePath: 'audio_replaced.bin');
    await WalWriteIntent.write(documents, old, [1, 2]);
    await WalFileManager.saveWals([old]);
    await File('${documents.path}/${old.filePath}').delete();
    await WalWriteIntent.retireFile(documents, old.filePath!);
    final replacement = Wal.fromJson(old.toJson())
      ..status = WalStatus.miss
      ..totalFrames = 2;
    await WalWriteIntent.write(documents, replacement, [3, 4]);
    final sync = LocalWalSyncImpl(_Listener(), deltaIndexAllowed: () async => true);
    await sync.loadForOnDeviceWorker();
    expect(sync.testWals.single.status, WalStatus.miss);
    expect(sync.testWals.single.totalFrames, 2);
    expect(await sync.hasDurableWal(sync.testWals.single, admittedGeneration: 0), isFalse);
    expect(await WalWriteIntent.exists(documents, replacement.filePath!), isTrue);
    await sync.persistRetryMetadata(sync.testWals.single);
    addTearDown((await sync.indexWorkerForTesting)!.close);
    expect((await WalFileManager.loadIndexedWals()).single.totalFrames, 2);
    expect(await WalWriteIntent.exists(documents, replacement.filePath!), isFalse);
  });
  test('deletion racing file creation cannot remove the only intent before bytes arrive', () async {
    final wal = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_creating.bin');
    final entered = Completer<void>(), release = Completer<void>();
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (rows) async {
      await WalFileManager.saveWals(rows);
    });
    sync.testWals = [wal];
    final writing = IOOverrides.runZoned(() => WalWriteIntent.write(documents, wal, [1, 2]), createFile: (path) {
      final real = Zone.root.run(() => File(path));
      return path.endsWith('/${wal.filePath}') ? _CreationBarrierFile(real, entered, release) : real;
    });
    await entered.future;
    final deleting = sync.deleteWal(wal);
    await pumpEventQueue(times: 100);
    release.complete();
    await writing;
    await deleting;
    expect(await File('${documents.path}/${wal.filePath}').exists(), isFalse,
        reason: 'a successful user delete must not be followed by an untracked late creation');
    expect(await WalFileManager.loadWals(), isEmpty);
  });
  test('device chunks refuse to create ownerless audio before admission', () async {
    await SharedPreferencesUtil().saveString('uid', '');
    final sync = LocalWalSyncImpl(_Listener(),
        freeDiskBytes: () async => 64 << 30,
        persistWals: (rows) async {
          await WalFileManager.saveWals(rows);
        });
    await expectLater(
        sync.persistDeviceChunk(
            source: Wal(timerStart: 1, codec: BleAudioCodec.opus, seconds: 10, device: 'pendant'),
            frames: [
              [1, 2]
            ],
            timerStart: 1,
            admittedGeneration: 0,
            nextCollisionSequence: () => 1),
        throwsStateError);
    expect(await documents.list().where((f) => f.path.split('/').last.startsWith('audio_')).length, 0);
  });

  test('an account switch during load still establishes the shared index namespace', () async {
    final old = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_owner_a.bin');
    await File('${documents.path}/${old.filePath}').writeAsBytes([1, 2]);
    await WalFileManager.saveWals([old]);
    final entered = Completer<void>(), release = Completer<void>();
    final sync = LocalWalSyncImpl(_Listener(),
        deltaIndexAllowed: () async => true,
        loadWals: () async {
          final rows = await WalFileManager.loadWals();
          entered.complete();
          await release.future;
          return rows;
        });
    sync.start();
    await entered.future;
    sync.clearUserData();
    await SharedPreferencesUtil().saveString('uid', 'owner-b');
    release.complete();
    await sync.walReady;
    final added = Wal(
        timerStart: 2,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-b',
        filePath: 'audio_owner_b.bin');
    await WalWriteIntent.write(documents, added, [3, 4]);
    await sync.addExternalWal(added, admittedGeneration: sync.sessionGeneration);
    await sync.stop();
    addTearDown((await sync.indexWorkerForTesting)!.close);
    expect((await WalFileManager.loadIndexedWals()).map((w) => w.filePath), [old.filePath, added.filePath]);
    expect(sync.testWals.every((w) => w.ownerUid == 'owner-b'), isTrue);
  });

  for (final accountPurge in [false, true]) {
    test('a ${accountPurge ? 'purge' : 'delete'} during live write cannot resurrect its memory row', () async {
      final live = Wal(
          timerStart: 1,
          codec: BleAudioCodec.opus,
          seconds: 10,
          device: 'pendant',
          ownerUid: 'owner-a',
          totalFrames: 1,
          data: [
            [1, 2]
          ]);
      final name = live.getFileName();
      final entered = Completer<void>(), release = Completer<void>();
      final sync = LocalWalSyncImpl(_Listener(),
          freeDiskBytes: () async => 64 << 30,
          persistWals: (rows) async {
            await WalFileManager.saveWals(rows);
          });
      sync.testWals = [live];
      final writing = IOOverrides.runZoned(() => sync.stop(), createFile: (path) {
        final real = Zone.root.run(() => File(path));
        return path.endsWith('/$name') ? _CreationBarrierFile(real, entered, release) : real;
      });
      await entered.future;
      final deleting = accountPurge ? sync.purgeAccountWals('owner-a') : sync.deleteWal(live);
      await pumpEventQueue(times: 100);
      release.complete();
      await writing;
      await deleting;
      expect(await File('${documents.path}/$name').exists(), isFalse);
      expect(await WalFileManager.loadWals(), isEmpty);
    });
  }

  test('legacy migration cannot overwrite a newer file registration', () async {
    final old = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_initial.bin');
    await File('${documents.path}/${old.filePath}').writeAsBytes([1, 2]);
    await WalFileManager.saveWals([old]);
    final legacy = File('${documents.path}/audio_limitless_opus_16000_1_fs320_r1_1794741663000.bin');
    await legacy.writeAsBytes([1, 2]);
    await SharedPreferencesUtil().saveStringList('flash_page_pending_uploads', [legacy.path]);
    final entered = Completer<void>(), release = Completer<void>();
    WalFileManager.beforeLegacyMigrationSaveForTesting = () async {
      entered.complete();
      await release.future;
    };
    final added = Wal(
        timerStart: 2,
        codec: BleAudioCodec.opus,
        seconds: 10,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        filePath: 'audio_during_migration.bin');
    var savedBeforeRelease = false;
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (rows) async {
      if (!release.isCompleted && rows.any((w) => w.filePath == added.filePath)) savedBeforeRelease = true;
      await WalFileManager.saveWals(rows);
    });
    sync.start();
    await entered.future;
    await WalWriteIntent.write(documents, added, [3, 4]);
    final adding = sync.addExternalWal(added, admittedGeneration: 0);
    await pumpEventQueue(times: 100);
    release.complete();
    await adding;
    await sync.walReady;
    await sync.stop();
    expect(savedBeforeRelease, isFalse, reason: 'registration must wait through migration and reload');
    expect((await WalFileManager.loadIndexedWals()).map((w) => w.filePath), contains(added.filePath));
  });
  for (final failCommit in [false, true]) {
    test('shared-file deletion transfers its intent without resurrecting the deleted row (failure=$failCommit)',
        () async {
      final deleted = Wal(
          timerStart: 1,
          codec: BleAudioCodec.opus,
          seconds: 10,
          storage: WalStorage.disk,
          ownerUid: 'owner-a',
          filePath: 'audio_shared.bin');
      await WalWriteIntent.write(documents, deleted, [1, 2]);
      final survivor = Wal(
          timerStart: 2,
          codec: BleAudioCodec.opus,
          seconds: 10,
          storage: WalStorage.disk,
          ownerUid: 'owner-a',
          filePath: deleted.filePath);
      await WalFileManager.saveWals([survivor]);
      final sync = LocalWalSyncImpl(_Listener(), persistWals: (rows) async {
        if (failCommit) throw const FileSystemException('injected shared delete index failure');
        await WalFileManager.saveWals(rows);
      });
      sync.testWals = [deleted, survivor];
      if (failCommit) {
        await expectLater(sync.deleteWal(deleted), throwsA(isA<FileSystemException>()));
      } else {
        await sync.deleteWal(deleted);
      }
      expect((await WalFileManager.loadWals()).map((w) => w.id), [survivor.id]);
      expect(await File('${documents.path}/${survivor.filePath}').readAsBytes(), [1, 2]);
      expect(await WalWriteIntent.exists(documents, survivor.filePath!), failCommit);
    });
  }

  test('failed admission completes ready with an error and keeps all subsequent saves closed', () async {
    final original = jsonEncode({
      'version': 1,
      'wals': [
        {'file_path': 'audio_uncertain.bin'}
      ]
    });
    final main = File('${documents.path}/wals.json');
    await main.writeAsString(original);
    WalFileManager.quarantineRenameForTesting = (_) async => throw const FileSystemException('rename denied');
    addTearDown(() => WalFileManager.quarantineRenameForTesting = null);
    final sync = LocalWalSyncImpl(_Listener());
    await IOOverrides.runZoned(() async {
      sync.start();
      await expectLater(sync.walReady.timeout(const Duration(seconds: 2)), throwsA(isA<FileSystemException>()));
      await expectLater(
          sync.addExternalWal(Wal(timerStart: 2, codec: BleAudioCodec.opus, seconds: 10), admittedGeneration: 0),
          throwsA(isA<FileSystemException>()));
      await expectLater(sync.stop(), throwsA(isA<FileSystemException>()));
    }, createFile: (path) {
      if (path.contains('wals.json.corrupt-')) return _UnwritableArchive();
      return Zone.root.run(() => File(path));
    });
    expect(await main.readAsString(), original);
  });

  test('live ring replay preserves its fsynced file hash and exact write transaction', () async {
    final sync = failingLedger();
    final live = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        ownerUid: 'owner-a',
        device: 'pendant',
        totalFrames: 2,
        data: [
          [1, 2],
          [3, 4]
        ],
        liveRingId: 42,
        liveOrdinalStart: 0,
        liveOrdinalEnd: 2);
    sync.testWals = [live];
    await expectLater(sync.stop(), throwsA(isA<FileSystemException>()));
    final recovered = (await WalFileManager.loadWals()).single;
    expect(recovered.fileSha256, isNotNull);
    expect(recovered.fileSha256, live.fileSha256);
    expect(recovered.liveDeviceId, 'pendant');
    expect(recovered.fileWriteId, live.fileWriteId);
    expect(recovered.fileWriteId, isNotNull);
  });
}
