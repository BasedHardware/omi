import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}

  @override
  void onWalUpdated() {}
}

class _LocalSyncs {
  _LocalSyncs(this.phone);

  final LocalWalSyncImpl phone;

  Future<List<Wal>> getAllWals() => phone.getAllWals();

  Future<void> deleteAllSyncedWals() => phone.deleteAllSyncedWals();

  Future<void> deleteAllPendingWals() => phone.deleteAllPendingWals();

  Future<void> deleteAllCorruptedWals() => phone.deleteAllCorruptedWals();

  Future<void> deleteWal(Wal wal) => phone.deleteWal(wal);

  Future<SyncLocalFilesResponse?> syncWal({
    required Wal wal,
    IWalSyncProgressListener? progress,
  }) =>
      phone.syncWal(wal: wal, progress: progress);
}

class _WalService implements IWalService {
  _WalService(this.syncs);

  final _LocalSyncs syncs;

  @override
  dynamic getSyncs() => syncs;

  @override
  void start() {}

  @override
  Future<void> stop() async {}

  @override
  void subscribe(IWalServiceListener subscription, Object context) {}

  @override
  void unsubscribe(Object context) {}
}

Wal _wal({required int timerStart, required String? filePath}) {
  return Wal(
    timerStart: timerStart,
    codec: BleAudioCodec.opus,
    seconds: 60,
    status: WalStatus.miss,
    storage: WalStorage.disk,
    device: 'omi',
    filePath: filePath,
  );
}

SyncUploadGate _offlineGate() {
  return SyncUploadGate(
    limiter: SyncRateLimiter.instance,
    uploader: (files,
        {onUploadProgress,
        conversationId,
        claimLiveCapture = false,
        syncLane = SyncUploadLane.fresh,
        replaceTranscript = false}) async {
      throw StateError('unexpected upload in terminal WAL-state test');
    },
    fairUseStatusLoader: () async => {'stage': 'none'},
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late LocalWalSyncImpl localSync;
  SyncProvider? provider;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    tempDir = await Directory.systemTemp.createTemp('terminal_wal_state_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();

    localSync = LocalWalSyncImpl(_Listener(), uploadGate: _offlineGate());
  });

  tearDown(() async {
    provider?.dispose();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    SyncRateLimiter.instance.clear();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  test('terminal corruption leaves Pending but remains visible and individually manageable', () async {
    final missingFile = _wal(timerStart: 1000, filePath: 'missing_audio.bin');
    missingFile
      ..isSyncing = true
      ..syncStartedAt = DateTime.now()
      ..syncEtaSeconds = 10
      ..syncSpeedKBps = 12;
    localSync.testWals = [missingFile];

    final syncProvider = SyncProvider(
      walService: _WalService(_LocalSyncs(localSync)),
      uploadGate: _offlineGate(),
      startBackgroundSync: false,
    );
    provider = syncProvider;
    await syncProvider.initialized;
    expect(syncProvider.pendingWals, [missingFile]);

    await localSync.syncAll();
    expect(missingFile.status, WalStatus.corrupted);
    expect(missingFile.isSyncing, isFalse);
    expect(missingFile.syncStartedAt, isNull);
    expect(missingFile.syncEtaSeconds, isNull);
    expect(missingFile.syncSpeedKBps, isNull);

    // A persisted stale flag must not reclassify or lock a terminal row.
    missingFile.isSyncing = true;

    final retryable = _wal(timerStart: 2000, filePath: null);
    localSync.testWals = [missingFile, retryable];
    await syncProvider.refreshWals();

    expect(syncProvider.pendingWals, [retryable]);
    expect(syncProvider.pendingStatusCount, 1);
    expect(syncProvider.filteredByStatusWals, [retryable]);
    expect(syncProvider.pendingDeletableWals, [retryable]);
    expect(syncProvider.corruptedWals, [missingFile]);
    expect(syncProvider.corruptedStatusCount, 1);
    expect(syncProvider.needsAttentionWalsCount, 1);
    expect(syncProvider.walsForDisplayFilter(WalDisplayFilter.pending), [retryable]);
    expect(syncProvider.walsForDisplayFilter(WalDisplayFilter.all), containsAll([missingFile, retryable]));

    syncProvider.setStatusFilter(WalStatusFilter.corrupted);
    expect(syncProvider.filteredByStatusWals, [missingFile]);

    await syncProvider.deleteAllPendingWals();

    expect(syncProvider.allWals, [missingFile]);
    expect(syncProvider.pendingWals, isEmpty);
    expect(syncProvider.needsAttentionWalsCount, 1);

    await syncProvider.deleteAllClearableWals();

    expect(syncProvider.allWals, isEmpty);
  });

  test('a recording refused for being older than the recovery window is terminal, not pending', () async {
    // #10975: the server answers 422 `backfill_lookback_exceeded` for a capture
    // past SYNC_BACKFILL_MAX_AGE_SECONDS. Retrying can never succeed, so the
    // recording must leave the pending pool instead of being offered as work
    // sync can still complete.
    final tooOld = _wal(timerStart: 1000, filePath: 'too_old_audio.bin')..markOutsideRecoveryWindow();
    final retryable = _wal(timerStart: 2000, filePath: 'retryable_audio.bin');
    localSync.testWals = [tooOld, retryable];

    final syncProvider = SyncProvider(
      walService: _WalService(_LocalSyncs(localSync)),
      uploadGate: _offlineGate(),
      startBackgroundSync: false,
    );
    provider = syncProvider;
    await syncProvider.initialized;

    // A persisted stale flag must not reclassify or lock a terminal row.
    tooOld.isSyncing = true;

    expect(syncProvider.pendingWals, [retryable]);
    expect(syncProvider.pendingDeletableWals, [retryable]);
    expect(syncProvider.walsForDisplayFilter(WalDisplayFilter.pending), [retryable]);
    expect(syncProvider.corruptedWals, [tooOld], reason: 'it belongs with the terminal, non-retryable recordings');
    expect(syncProvider.needsAttentionWalsCount, 1);
    expect(syncProvider.walsForDisplayFilter(WalDisplayFilter.all), containsAll([tooOld, retryable]));

    await syncProvider.deleteAllClearableWals();

    expect(syncProvider.allWals, isEmpty, reason: 'Clear All must still be able to remove it');
  });

  test('raw pendant transfer ranges stay hidden until assembled', () async {
    final rawRange = Wal(
      timerStart: 1000,
      codec: BleAudioCodec.opus,
      seconds: 1,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      device: 'cv1',
      filePath: 'raw.bin',
      sourceId: 'ring_10_11',
    );
    final assembledArchive = Wal(
      timerStart: 1000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      device: 'cv1',
      filePath: 'archive.bin',
      sourceId: 'archive_ring_10_40_1000',
    );
    localSync.testWals = [rawRange, assembledArchive];

    final syncProvider = SyncProvider(
      walService: _WalService(_LocalSyncs(localSync)),
      uploadGate: _offlineGate(),
      startBackgroundSync: false,
    );
    provider = syncProvider;
    await syncProvider.initialized;

    expect(syncProvider.allWals, [rawRange, assembledArchive]);
    expect(syncProvider.userVisibleWals, hasLength(1));
    final logicalArchive = syncProvider.userVisibleWals.single;
    expect(syncProvider.isLogicalRingArchiveDisplayWal(logicalArchive), isTrue);
    expect(syncProvider.logicalRingArchiveMembersForTest(logicalArchive), [assembledArchive]);
    expect(syncProvider.pendingWals, [logicalArchive]);
    expect(syncProvider.displaySortedWals, [logicalArchive]);
    expect(syncProvider.walsForDisplayFilter(WalDisplayFilter.all), [logicalArchive]);
  });

  test('logical archive sync submits every physical part in one job while row deletion stays non-destructive',
      () async {
    SharedPreferencesUtil().conversationSilenceDuration = 120;
    final uploadedBatches = <List<String>>[];
    final gate = SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      uploader: (
        files, {
        onUploadProgress,
        conversationId,
        syncLane = SyncUploadLane.fresh,
        replaceTranscript = false,
      }) async {
        uploadedBatches.add(files.map((file) => file.path).toList());
        return UploadFilesResult.done(
          SyncLocalFilesResponse(
            newConversationIds: ['logical-archive-conversation'],
            updatedConversationIds: [],
          ),
        );
      },
      fairUseStatusLoader: () async => {'stage': 'none'},
    );
    localSync = LocalWalSyncImpl(_Listener(), uploadGate: gate);
    final archives = <Wal>[];
    for (var index = 0; index < 10; index++) {
      final timerStart = 1000 + index * 300;
      final fileName = 'logical-archive-$index.bin';
      File('${tempDir.path}/$fileName').writeAsBytesSync([1, 0, 0, 0, index]);
      archives.add(
        Wal(
          timerStart: timerStart,
          codec: BleAudioCodec.opus,
          seconds: 300,
          captureEndSeconds: timerStart + 300,
          totalFrames: 1,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          originalStorage: WalStorage.sdcard,
          device: 'cv1',
          filePath: fileName,
          sourceId: 'archive2_ring_${index * 100}_${(index + 1) * 100}_$timerStart',
          uploadIntent: WalUploadIntent.historicalBackfill,
        ),
      );
    }
    localSync.testWals = archives;
    final syncProvider = SyncProvider(
      walService: _WalService(_LocalSyncs(localSync)),
      uploadGate: gate,
      startBackgroundSync: false,
    );
    provider = syncProvider;
    await syncProvider.initialized;
    final logical = syncProvider.userVisibleWals.single;

    await syncProvider.deleteWal(logical);

    expect(localSync.testWals, archives);
    expect(archives.every((wal) => File('${tempDir.path}/${wal.filePath}').existsSync()), isTrue);

    await syncProvider.syncWal(logical);

    expect(uploadedBatches, hasLength(1));
    expect(uploadedBatches.single, hasLength(10));
    expect(archives.every((wal) => wal.status == WalStatus.synced), isTrue);
  });
}
