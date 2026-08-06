import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Fake syncs object returned by [_FakeWalService.getSyncs]. SyncProvider treats
/// getSyncs() as dynamic, so only the members it actually calls are needed here.
class _FakeSyncs {
  final List<Wal> wals;
  int syncWalCalls = 0;
  int deleteWalCalls = 0;
  final List<Wal> selectedSyncWals = [];
  int syncAllCalls = 0;
  int syncPhoneWalsCalls = 0;
  int syncAuthorizedRingRecoveryCalls = 0;
  int requestedRingDrains = 0;
  bool ringAudioTailActive = false;
  bool storageSyncing = false;
  int nextRingTargetSeq = 200;
  SyncLocalFilesResponse? nextSyncResult;
  Completer<SyncLocalFilesResponse?>? hangSyncWal;
  Object? syncWalError;
  Completer<RingBacklogDrainReceipt?>? ringBacklogDrain;
  RingBacklogDrainReceipt? pendingAutomaticRingBacklogReceipt;
  final List<AuthorizedRecoverySyncResult> authorizedRecoveryResults = [];
  final List<RingBacklogDrainReceipt> authorizedReceipts = [];
  final List<bool> phoneSyncIncludeBackfill = [];

  _FakeSyncs(this.wals);

  Future<List<Wal>> getAllWals() async => List<Wal>.of(wals);

  Future<void> refreshWalsFromDevice({String? firmwareVersion}) async {}

  bool get isStorageSyncing => storageSyncing;
  bool get isSdCardSyncing => false;
  bool get isRingAudioTailActive => ringAudioTailActive;

  SyncLocalFilesResponse? get accumulatedResponse => null;

  void cancelSync() {}

  Future<RingBacklogDrainReceipt?>? requestActiveRingBacklogDrain({
    IWalSyncProgressListener? progress,
  }) {
    if (!ringAudioTailActive) return null;
    requestedRingDrains++;
    return ringBacklogDrain?.future ??
        Future<RingBacklogDrainReceipt?>.value(
          RingBacklogDrainReceipt(
            deviceId: 'cv1-test',
            targetWriteSeq: nextRingTargetSeq,
          ),
        );
  }

  Future<SyncLocalFilesResponse?> syncPhoneWals({
    IWalSyncProgressListener? progress,
    bool includeBackfill = false,
  }) async {
    syncPhoneWalsCalls++;
    phoneSyncIncludeBackfill.add(includeBackfill);
    for (final wal in wals.where((wal) => wal.status == WalStatus.miss)) {
      wal.status = WalStatus.uploaded;
      wal.jobId = 'job-phone-only';
    }
    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  Future<AuthorizedRecoverySyncResult> syncAuthorizedRingRecovery({
    required RingBacklogDrainReceipt receipt,
    IWalSyncProgressListener? progress,
  }) async {
    syncAuthorizedRingRecoveryCalls++;
    authorizedReceipts.add(receipt);
    final result = authorizedRecoveryResults.isEmpty
        ? const AuthorizedRecoverySyncResult(
            response: null,
            hasDeferredRecovery: false,
          )
        : authorizedRecoveryResults.removeAt(0);
    if ((result.response?.localUploadFailures ?? 0) == 0 && !result.hasDeferredRecovery) {
      for (final wal in wals.where((wal) => wal.status == WalStatus.miss)) {
        wal.status = WalStatus.synced;
      }
    }
    return result;
  }

  void completeAutomaticRingBacklogReceipt(
    RingBacklogDrainReceipt receipt,
  ) {
    if (identical(pendingAutomaticRingBacklogReceipt, receipt)) {
      pendingAutomaticRingBacklogReceipt = null;
    }
  }

  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    syncAllCalls++;
    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    syncWalCalls++;
    selectedSyncWals.add(wal);
    final error = syncWalError;
    if (error != null) throw error;
    final hang = hangSyncWal;
    if (hang != null) return hang.future;
    final result = nextSyncResult ?? SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    if (result.localUploadFailures == 0 && result.newConversationIds.isEmpty) {
      // Mirror a 202 accepted upload: WAL becomes `uploaded`, no conversations yet.
      wal.status = WalStatus.uploaded;
      wal.jobId = 'job-202';
    }
    return result;
  }

  Future<void> deleteWal(Wal wal) async {
    deleteWalCalls++;
    wals.remove(wal);
  }
}

class _FakeWalService implements IWalService {
  final _FakeSyncs syncs;
  _FakeWalService(this.syncs);

  @override
  void start() {}

  @override
  Future stop() async {}

  @override
  void subscribe(IWalServiceListener subscription, Object context) {}

  @override
  void unsubscribe(Object context) {}

  @override
  dynamic getSyncs() => syncs;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('syncWal 202 wakes the transfer coordinator for reconciliation', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final wal = Wal(timerStart: 1000, codec: BleAudioCodec.pcm16, seconds: 30, status: WalStatus.miss);
    final syncs = _FakeSyncs([wal]);
    final wakes = <WakeTrigger>[];

    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: true,
      waitForWalReady: (_) async {},
      startRecovery: () async {},
      wakeTransfer: (trigger) async {
        wakes.add(trigger);
      },
    );
    await provider.initialized;

    await provider.syncWal(wal);

    expect(syncs.syncWalCalls, 1);
    expect(
        wakes,
        [
          WakeTrigger.cooldownElapsed,
        ],
        reason: 'successful syncWal must wake coordinator so uploaded WALs reconcile');
    provider.dispose();
  });

  test('partial localUploadFailures still complete then surface error', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final wal = Wal(timerStart: 1000, codec: BleAudioCodec.pcm16, seconds: 30, status: WalStatus.miss);
    final syncs = _FakeSyncs([wal])
      ..nextSyncResult = SyncLocalFilesResponse(
        newConversationIds: [],
        updatedConversationIds: [],
        localUploadFailures: 1,
      );
    final wakes = <WakeTrigger>[];

    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: true,
      waitForWalReady: (_) async {},
      startRecovery: () async {},
      wakeTransfer: (trigger) async {
        wakes.add(trigger);
      },
    );
    await provider.initialized;

    await provider.syncWal(wal);

    expect(provider.syncState.hasError, isTrue);
    expect(provider.syncError, contains('Upload failed'));
    // Still wakes — successful HTTP return with partial failures may include uploads.
    expect(wakes, [WakeTrigger.cooldownElapsed]);
    provider.dispose();
  });

  test('syncWal during an in-flight sync queues the exact row instead of widening authority', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final wal = Wal(timerStart: 1000, codec: BleAudioCodec.pcm16, seconds: 30, status: WalStatus.miss);
    final other = Wal(timerStart: 2000, codec: BleAudioCodec.pcm16, seconds: 30, status: WalStatus.miss);
    final hang = Completer<SyncLocalFilesResponse?>();
    final syncs = _FakeSyncs([wal, other])..hangSyncWal = hang;
    final wakes = <WakeTrigger>[];

    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: true,
      waitForWalReady: (_) async {},
      startRecovery: () async {},
      wakeTransfer: (trigger) async {
        wakes.add(trigger);
      },
    );
    await provider.initialized;

    final first = provider.syncWal(wal);
    await Future<void>.delayed(Duration.zero);
    expect(provider.isSyncing, isTrue);
    expect(syncs.syncWalCalls, 1);

    final second = provider.syncWal(other);
    await Future<void>.delayed(Duration.zero);

    expect(syncs.syncWalCalls, 1, reason: 'contended syncWal must not start a parallel upload');
    expect(wakes, isEmpty);

    syncs.hangSyncWal = null;
    hang.complete(SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []));
    await first;
    await second;

    expect(syncs.syncWalCalls, 2);
    expect(wakes, [WakeTrigger.cooldownElapsed, WakeTrigger.cooldownElapsed]);
    provider.dispose();
  });

  test('an upload cooldown does not block pulling audio off the device', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
    // syncWal dispatches the whole transfer, including the device-download
    // phases, which consume no upload quota. Refusing it here strands audio on
    // a device with finite storage; the upload phases carry their own guard.
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 600, reason: RateLimitReason.backendBusy);
    addTearDown(SyncRateLimiter.instance.clear);

    final wal = Wal(timerStart: 1000, codec: BleAudioCodec.pcm16, seconds: 30, status: WalStatus.miss);
    final syncs = _FakeSyncs([wal]);
    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: true,
      waitForWalReady: (_) async {},
      startRecovery: () async {},
      wakeTransfer: (_) async {},
    );
    await provider.initialized;

    await provider.syncWal(wal);

    expect(SyncRateLimiter.instance.isLimited, isTrue);
    expect(syncs.syncWalCalls, 1, reason: 'device recovery must stay available during an upload cooldown');
    provider.dispose();
  });

  test('single-row retry during an active tail preserves exact phone row identity', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final wal = Wal(
      timerStart: 1000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.miss,
      storage: WalStorage.disk,
    );
    final syncs = _FakeSyncs([wal])..ringAudioTailActive = true;
    final wakes = <WakeTrigger>[];
    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: true,
      waitForWalReady: (_) async {},
      startRecovery: () async {},
      wakeTransfer: (trigger) async => wakes.add(trigger),
    );
    await provider.initialized;

    await provider.syncWal(wal);

    expect(wakes, [WakeTrigger.cooldownElapsed]);
    expect(syncs.syncWalCalls, 1);
    expect(syncs.requestedRingDrains, 0);
    expect(syncs.syncAllCalls, 0);
    provider.dispose();
  });

  test('failed-row retry does not widen into a manual device snapshot', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final wal = Wal(
      timerStart: 1000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.miss,
      storage: WalStorage.disk,
    );
    final syncs = _FakeSyncs([wal])..syncWalError = StateError('row upload failed');
    final wakes = <WakeTrigger>[];
    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: true,
      waitForWalReady: (_) async {},
      startRecovery: () async {},
      wakeTransfer: (trigger) async => wakes.add(trigger),
    );
    await provider.initialized;

    await provider.syncWal(wal);
    expect(provider.failedWal, same(wal));

    syncs
      ..syncWalError = null
      ..ringAudioTailActive = true;
    await provider.retrySync();

    expect(syncs.syncWalCalls, 2);
    expect(syncs.requestedRingDrains, 0);
    expect(syncs.syncAllCalls, 0);
    expect(wakes, [WakeTrigger.cooldownElapsed]);
    provider.dispose();
  });

  test('selected device row stays scoped while the audio tail owns BLE', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final wal = Wal(
      timerStart: 1000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.miss,
      storage: WalStorage.sdcard,
      fileNum: -1,
    );
    final syncs = _FakeSyncs([wal])
      ..ringAudioTailActive = true
      ..storageSyncing = true;
    final wakes = <WakeTrigger>[];
    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: true,
      waitForWalReady: (_) async {},
      startRecovery: () async {},
      wakeTransfer: (trigger) async => wakes.add(trigger),
    );
    await provider.initialized;

    await provider.syncWal(wal);

    expect(provider.failedWal, same(wal));
    expect(syncs.syncWalCalls, 0);
    expect(syncs.requestedRingDrains, 0);
    expect(syncs.syncAllCalls, 0);
    expect(wakes, isEmpty);
    provider.dispose();
  });

  test('manual ring sync with auto-sync off waits for tail snapshot then uploads phone-only', () async {
    SharedPreferences.setMockInitialValues({'autoSyncOfflineRecordings': false});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final wal = Wal(
      timerStart: 1000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      sourceId: 'archive_ring_100_200_1000',
    );
    final tailDrain = Completer<RingBacklogDrainReceipt?>();
    final syncs = _FakeSyncs([wal])
      ..ringAudioTailActive = true
      ..storageSyncing = true
      ..ringBacklogDrain = tailDrain;
    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: false,
    );
    await provider.initialized;
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: provider.refreshWals,
      drain: provider.drainEligibleWalsForTest,
      autoUploadEnabled: () => SharedPreferencesUtil().autoSyncOfflineRecordings,
    );
    addTearDown(coordinator.dispose);
    addTearDown(provider.dispose);

    final manualSync = coordinator.wake(WakeTrigger.userRetry);
    await Future<void>.delayed(Duration.zero);

    expect(syncs.requestedRingDrains, 1);
    expect(syncs.syncPhoneWalsCalls, 0);
    expect(syncs.syncAllCalls, 0);

    tailDrain.complete(
      const RingBacklogDrainReceipt(
        deviceId: 'cv1-test',
        targetWriteSeq: 200,
      ),
    );
    await manualSync;

    expect(syncs.syncAuthorizedRingRecoveryCalls, 1);
    expect(syncs.syncPhoneWalsCalls, 0);
    expect(syncs.syncAllCalls, 0, reason: 'the active tail must remain the only ring reader');
    expect(wal.status, WalStatus.synced);
  });

  test('cloud retry reuses one completed manual snapshot receipt', () async {
    SharedPreferences.setMockInitialValues({'autoSyncOfflineRecordings': false});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final wal = Wal(
      timerStart: 1000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      sourceId: 'ring_100_200',
      device: 'cv1-test',
    );
    final syncs = _FakeSyncs([wal])
      ..ringAudioTailActive = true
      ..storageSyncing = true
      ..authorizedRecoveryResults.add(
        AuthorizedRecoverySyncResult(
          response: SyncLocalFilesResponse(
            newConversationIds: [],
            updatedConversationIds: [],
            localUploadFailures: 1,
          ),
          hasDeferredRecovery: true,
        ),
      )
      ..authorizedRecoveryResults.add(
        const AuthorizedRecoverySyncResult(
          response: null,
          hasDeferredRecovery: false,
        ),
      );
    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: false,
    );
    await provider.initialized;
    void Function()? retry;
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: provider.refreshWals,
      drain: provider.drainEligibleWalsForTest,
      autoUploadEnabled: () => false,
      scheduleCooldown: (_, callback) => retry = callback,
    );
    addTearDown(coordinator.dispose);
    addTearDown(provider.dispose);

    await coordinator.wake(WakeTrigger.userRetry);

    expect(syncs.requestedRingDrains, 1);
    expect(syncs.syncAuthorizedRingRecoveryCalls, 1);
    expect(retry, isNotNull);

    syncs.nextRingTargetSeq = 999;
    retry!();
    await Future<void>.delayed(const Duration(milliseconds: 10));

    expect(syncs.requestedRingDrains, 1, reason: 'backend retry must not latch a newer pendant writeSeq');
    expect(syncs.syncAuthorizedRingRecoveryCalls, 2);
    expect(
      syncs.authorizedReceipts.map((receipt) => receipt.targetWriteSeq),
      [200, 200],
    );
    expect(syncs.syncAllCalls, 0);
  });

  test('foreground wake consumes a completed automatic receipt without a second reader', () async {
    SharedPreferences.setMockInitialValues({'autoSyncOfflineRecordings': true});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    const receipt = RingBacklogDrainReceipt(
      deviceId: 'cv1-test',
      targetWriteSeq: 300,
    );
    final wal = Wal(
      timerStart: 1000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      sourceId: 'archive2_ring_200_300_1000',
      device: 'cv1-test',
    );
    final syncs = _FakeSyncs([wal])
      ..ringAudioTailActive = true
      ..storageSyncing = true
      ..pendingAutomaticRingBacklogReceipt = receipt;
    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: false,
    );
    addTearDown(provider.dispose);
    await provider.initialized;

    final result = await provider.drainEligibleWalsForTest(
      WakeTrigger.foregrounded,
    );

    expect(result.failed, isFalse);
    expect(syncs.syncAuthorizedRingRecoveryCalls, 1);
    expect(syncs.authorizedReceipts, [receipt]);
    expect(syncs.syncAllCalls, 0);
    expect(syncs.requestedRingDrains, 0);
    expect(syncs.pendingAutomaticRingBacklogReceipt, isNull);
  });

  test('ten adjacent physical ring archives present as one logical pending recording', () async {
    SharedPreferences.setMockInitialValues({'conversationSilenceDuration': 120});
    await SharedPreferencesUtil.init();
    final archives = List.generate(
      10,
      (index) => _ringArchive(
        timerStart: 1000 + index * 300,
        startSequence: index * 100,
        endSequence: (index + 1) * 100,
        playableSeconds: 5,
      ),
    );
    final syncs = _FakeSyncs(archives);
    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: false,
    );
    addTearDown(provider.dispose);
    await provider.initialized;

    expect(provider.userVisibleWals, hasLength(1));
    final logical = provider.userVisibleWals.single;
    expect(provider.isLogicalRingArchiveDisplayWal(logical), isTrue);
    expect(provider.logicalRingArchiveMembersForTest(logical), archives);
    expect(logical.seconds, 3000, reason: 'display duration is the wall-clock span, not compressed audio sum');
    expect(provider.pendingStatusCount, 1);
    expect(provider.readyToSyncRecordingCount, 1);
    expect(provider.processingRecordingCount, 0);
    expect(provider.missingWals, hasLength(10), reason: 'physical transport accounting remains independent');

    for (final archive in archives) {
      archive.status = WalStatus.uploaded;
    }
    await provider.refreshWals();

    expect(provider.readyToSyncRecordingCount, 0);
    expect(provider.processingRecordingCount, 1);
    expect(provider.uploadedWals, hasLength(10), reason: 'server reconciliation still retains every physical member');
  });

  test('logical recording opens one materialized playback artifact', () async {
    SharedPreferences.setMockInitialValues({'conversationSilenceDuration': 120});
    await SharedPreferencesUtil.init();
    final archives = [
      _ringArchive(timerStart: 1000, startSequence: 0, endSequence: 100),
      _ringArchive(timerStart: 1300, startSequence: 100, endSequence: 200),
    ];
    var materializationCalls = 0;
    List<Wal>? materializedMembers;
    final provider = SyncProvider(
      walService: _FakeWalService(_FakeSyncs(archives)),
      startBackgroundSync: false,
      logicalArchivePlaybackMaterializer: (logicalWal, members) async {
        materializationCalls++;
        materializedMembers = members;
        return Wal(
          timerStart: logicalWal.timerStart,
          codec: logicalWal.codec,
          seconds: logicalWal.seconds,
          status: logicalWal.status,
          storage: WalStorage.disk,
          filePath: 'logical-playback.bin',
          device: logicalWal.device,
          sourceId: logicalWal.sourceId,
        );
      },
    );
    addTearDown(provider.dispose);
    await provider.initialized;

    final logical = provider.userVisibleWals.single;
    final first = await provider.resolveWalForDetail(logical);
    final second = await provider.resolveWalForDetail(logical);

    expect(materializedMembers, archives);
    expect(first, same(second));
    expect(provider.canPlayOrShareWal(first!), isTrue);
    expect(materializationCalls, 1);
  });

  test('backend-minimum silence boundary joins inside the boundary and splits at it', () async {
    SharedPreferences.setMockInitialValues({'conversationSilenceDuration': 30});
    await SharedPreferencesUtil.init();
    final archives = [
      _ringArchive(timerStart: 1000, startSequence: 0, endSequence: 100),
      _ringArchive(timerStart: 1390, startSequence: 100, endSequence: 200),
      _ringArchive(timerStart: 1810, startSequence: 200, endSequence: 300),
    ];
    final provider = SyncProvider(
      walService: _FakeWalService(_FakeSyncs(archives)),
      startBackgroundSync: false,
    );
    addTearDown(provider.dispose);
    await provider.initialized;

    expect(provider.userVisibleWals, hasLength(2));
    expect(provider.pendingStatusCount, 2);
    expect(provider.userVisibleWals.every(provider.isLogicalRingArchiveDisplayWal), isTrue);
    expect(provider.logicalRingArchiveMembersForTest(provider.userVisibleWals.first), archives.take(2));
  });

  test('a backwards device clock step keeps logical playback in pendant sequence order', () async {
    SharedPreferences.setMockInitialValues({'conversationSilenceDuration': 120});
    await SharedPreferencesUtil.init();
    final beforeRollback = _ringArchive(
      timerStart: 2000,
      startSequence: 0,
      endSequence: 100,
    );
    final afterRollback = _ringArchive(
      timerStart: 1000,
      startSequence: 100,
      endSequence: 200,
    );
    final provider = SyncProvider(
      walService: _FakeWalService(_FakeSyncs([beforeRollback, afterRollback])),
      startBackgroundSync: false,
    );
    addTearDown(provider.dispose);
    await provider.initialized;

    expect(provider.userVisibleWals, hasLength(1));
    expect(
      provider.logicalRingArchiveMembersForTest(provider.userVisibleWals.single),
      [beforeRollback, afterRollback],
      reason: 'display order follows immutable pendant sequence, not the corrected RTC',
    );
  });

  test('unlimited conversation setting uses the shared four-hour boundary', () async {
    SharedPreferences.setMockInitialValues({'conversationSilenceDuration': -1});
    await SharedPreferencesUtil.init();
    final archives = [
      _ringArchive(timerStart: 1000, startSequence: 0, endSequence: 100),
      _ringArchive(timerStart: 12100, startSequence: 100, endSequence: 200),
    ];
    final provider = SyncProvider(
      walService: _FakeWalService(_FakeSyncs(archives)),
      startBackgroundSync: false,
    );
    addTearDown(provider.dispose);
    await provider.initialized;

    expect(provider.userVisibleWals, hasLength(1));
    expect(provider.logicalRingArchiveMembersForTest(provider.userVisibleWals.single), archives);
  });

  test('conversation boundary preference change invalidates every logical display cache', () async {
    SharedPreferences.setMockInitialValues({'conversationSilenceDuration': 120});
    await SharedPreferencesUtil.init();
    final archives = [
      _ringArchive(timerStart: 1000, startSequence: 0, endSequence: 100),
      _ringArchive(timerStart: 1420, startSequence: 100, endSequence: 200),
    ];
    final provider = SyncProvider(
      walService: _FakeWalService(_FakeSyncs(archives)),
      startBackgroundSync: false,
    );
    addTearDown(provider.dispose);
    await provider.initialized;

    expect(provider.userVisibleWals, hasLength(2));
    expect(provider.pendingWals, hasLength(2));
    expect(provider.pendingStatusCount, 2);
    expect(provider.displaySortedWals, hasLength(2));

    SharedPreferencesUtil().conversationSilenceDuration = -1;

    expect(provider.userVisibleWals, hasLength(1));
    expect(provider.pendingWals, hasLength(1));
    expect(provider.pendingStatusCount, 1);
    expect(provider.displaySortedWals, hasLength(1));
    expect(provider.logicalRingArchiveMembersForTest(provider.displaySortedWals.single), archives);
  });

  test('logical archive surfaces corruption ahead of pending and uploaded members', () async {
    SharedPreferences.setMockInitialValues({'conversationSilenceDuration': 120});
    await SharedPreferencesUtil.init();
    final archives = [
      _ringArchive(timerStart: 1000, startSequence: 0, endSequence: 100)..status = WalStatus.uploaded,
      _ringArchive(timerStart: 1300, startSequence: 100, endSequence: 200)..status = WalStatus.miss,
      _ringArchive(timerStart: 1600, startSequence: 200, endSequence: 300)..status = WalStatus.corrupted,
    ];
    final provider = SyncProvider(
      walService: _FakeWalService(_FakeSyncs(archives)),
      startBackgroundSync: false,
    );
    addTearDown(provider.dispose);
    await provider.initialized;

    final logical = provider.userVisibleWals.single;
    expect(logical.status, WalStatus.corrupted);
    expect(logical.syncDisplayState, WalSyncDisplayState.corrupted);
    expect(provider.corruptedStatusCount, 1);
    expect(provider.pendingStatusCount, 0);
  });

  test('logical ring archive row cannot delete one physical part and sync resolves through its complete group',
      () async {
    SharedPreferences.setMockInitialValues({'conversationSilenceDuration': 120});
    await SharedPreferencesUtil.init();
    final archives = List.generate(
      10,
      (index) => _ringArchive(
        timerStart: 1000 + index * 300,
        startSequence: index * 100,
        endSequence: (index + 1) * 100,
      ),
    );
    archives.first.status = WalStatus.synced;
    final syncs = _FakeSyncs(archives);
    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      startBackgroundSync: false,
    );
    addTearDown(provider.dispose);
    await provider.initialized;
    final logical = provider.userVisibleWals.single;

    await provider.deleteWal(logical);

    expect(syncs.deleteWalCalls, 0);
    expect(syncs.wals, archives);
    expect(provider.canDeleteWal(logical), isFalse);

    await provider.syncWal(logical);

    expect(provider.logicalRingArchiveMembersForTest(logical), archives);
    expect(syncs.syncWalCalls, 1);
    expect(logical.status, WalStatus.miss);
    expect(syncs.selectedSyncWals.single, same(archives[1]));
    expect(syncs.selectedSyncWals.single, isNot(same(logical)));
  });
}

Wal _ringArchive({
  required int timerStart,
  required int startSequence,
  required int endSequence,
  int playableSeconds = 300,
}) =>
    Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.opus,
      seconds: playableSeconds,
      captureEndSeconds: timerStart + 300,
      totalFrames: 30000,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      device: 'cv1-test',
      sourceId: 'archive2_ring_${startSequence}_${endSequence}_$timerStart',
      filePath: 'archive-$startSequence-$endSequence.bin',
      uploadIntent: WalUploadIntent.historicalBackfill,
    );
