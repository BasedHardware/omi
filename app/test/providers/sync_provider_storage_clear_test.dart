import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/ring_drain_policy.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/services/wals/storage_clear.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/wal_syncs.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
  @override
  void onWalUpdated() {}
}

/// The pendant's 11 h ring: a reader that runs until cancelled and refuses a
/// clear while it reads, as the real reader does.
class _Ring extends RingStorageSyncImpl {
  _Ring() : super(_Listener());

  final events = <String>[];
  Completer<void>? _read;
  int reads = 0;
  final pending = Wal(
    timerStart: 1704067200,
    codec: BleAudioCodec.opus,
    seconds: 11 * 3600,
    storage: WalStorage.sdcard,
    status: WalStatus.miss,
    fileNum: -1,
    device: 'pendant',
  );

  void finishRead() {
    final read = _read;
    if (read != null && !read.isCompleted) read.complete();
  }

  @override
  bool get isSyncing => _read != null;
  @override
  Future<void> refreshWalsFromDevice() async {}
  @override
  Future<List<Wal>> getMissingWals() async => pending.status == WalStatus.miss ? [pending] : [];
  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    reads++;
    final read = _read = Completer<void>();
    await read.future;
    _read = null;
    return null;
  }

  @override
  void cancelSync() => finishRead();

  @override
  Future<void> deleteAllPendingWals() async {
    if (isSyncing) {
      events.add('clear-refused');
      return;
    }
    events.add('clear');
    pending.status = WalStatus.synced;
  }
}

class _Service implements IWalService {
  _Service(this.syncs);
  final WalSyncs syncs;
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

SyncUploadGate _offlineGate() => SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      uploader: (files,
          {onUploadProgress,
          conversationId,
          captureEvidence,
          recordingSessionId,
          audioStartSeconds,
          audioEndSeconds,
          claimLiveCapture = false,
          geolocation}) async {
        throw StateError('unexpected upload in storage-clear test');
      },
      fairUseStatusLoader: () async => {'stage': 'none'},
    );

Future<void> _settle() async {
  for (var i = 0; i < 5; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory tempDir;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
    tempDir = await Directory.systemTemp.createTemp('storage_clear_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => call.method == 'getApplicationDocumentsDirectory' ? tempDir.path : null,
    );
    await WalFileManager.init();
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    if (tempDir.existsSync()) await tempDir.delete(recursive: true);
  });

  test('deleting not-uploaded audio stops an active pendant read, clears phone and pendant, then resumes', () async {
    if (!ringDrainRecoveryEnabled) return;
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    Wal phoneWal(int ago, WalStatus status) => Wal(
          timerStart: now - ago,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: status,
          storage: WalStorage.disk,
          device: 'phone',
        );
    final phone = LocalWalSyncImpl(_Listener(), uploadGate: _offlineGate(), persistWals: (_) async {});
    final waiting = [phoneWal(600, WalStatus.miss), phoneWal(540, WalStatus.miss)];
    final uploaded = phoneWal(300, WalStatus.synced);
    // Accepted by the server, not settled: not "not uploaded", and its row is
    // the only handle reconciliation has on the job.
    final accepted = phoneWal(240, WalStatus.uploaded);
    phone.testWals = [...waiting, uploaded, accepted];
    final ring = _Ring();
    final syncs = WalSyncs(_Listener(), phoneSync: phone, ringSync: ring);
    final pendant = BtDevice(id: 'pendant', name: 'Omi', type: DeviceType.omi, rssi: -40);
    syncs.setDevice(pendant, firmwareVersion: '3.0.21');
    syncs.configureRingDrain(() => true);
    await _settle();
    expect(ring.isSyncing, isTrue, reason: 'the drain is reading the pendant when the user opens Manage Storage');

    final provider = SyncProvider(walService: _Service(syncs), uploadGate: _offlineGate(), startBackgroundSync: false);
    addTearDown(() {
      ring.finishRead();
      syncs.disableRingDrain();
      provider.dispose();
    });
    await provider.initialized;
    expect(provider.storageAmounts.devicePendingSeconds, 11 * 3600);
    expect(provider.storageAmounts.phonePendingSeconds, 120);

    final phases = <StorageClearPhase>[];
    final outcome = await provider.clearStorage(
      StorageClearScope.notUploaded,
      firmwareVersion: '3.0.21',
      onProgress: (p) => phases.add(p.phase),
    );

    expect(ring.events, ['clear'], reason: 'the read stopped before the ring clear, so it was not refused');
    expect(outcome.complete, isTrue);
    expect(outcome.deletedSeconds, 11 * 3600 + 120);
    expect(phases.first, StorageClearPhase.stopping);
    expect(phases, contains(StorageClearPhase.deleting));
    expect(phases.last, StorageClearPhase.verifying);
    expect(provider.allWals, unorderedEquals([uploaded, accepted]), reason: 'uploaded audio is not part of this scope');
    expect(syncs.transfersHeldForClear, isFalse, reason: 'the hold is released on the way out');

    final readsBefore = ring.reads;
    ring.pending.status = WalStatus.miss; // the pendant kept recording
    unawaited(syncs.wakeRingDrain());
    await _settle();
    expect(ring.reads, readsBefore + 1, reason: 'the drain resumes after the clear');
  });

  test('freeing space removes only uploaded copies and never stops the pendant read', () async {
    if (!ringDrainRecoveryEnabled) return;
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final phone = LocalWalSyncImpl(_Listener(), uploadGate: _offlineGate(), persistWals: (_) async {});
    final waiting = Wal(
        timerStart: now - 600,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'phone');
    final uploaded = Wal(
        timerStart: now - 300,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.synced,
        storage: WalStorage.disk,
        device: 'phone');
    phone.testWals = [waiting, uploaded];
    final ring = _Ring();
    final syncs = WalSyncs(_Listener(), phoneSync: phone, ringSync: ring);
    syncs.setDevice(BtDevice(id: 'pendant', name: 'Omi', type: DeviceType.omi, rssi: -40), firmwareVersion: '3.0.21');
    syncs.configureRingDrain(() => true);
    await _settle();
    final provider = SyncProvider(walService: _Service(syncs), uploadGate: _offlineGate(), startBackgroundSync: false);
    addTearDown(() {
      ring.finishRead();
      syncs.disableRingDrain();
      provider.dispose();
    });
    await provider.initialized;
    final outcome = await provider.clearStorage(StorageClearScope.uploaded);

    expect(outcome.complete, isTrue);
    expect(outcome.deletedSeconds, 60);
    expect(ring.isSyncing, isTrue, reason: 'nothing that is lost by deleting was touched');
    expect(provider.allWals, containsAll([ring.pending, waiting]));
    expect(provider.allWals, isNot(contains(uploaded)));
  });

  test('an upload started outside the coordinator is waited for, and a clear never deletes it', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    Wal waitingWal(int ago) => Wal(
        timerStart: now - ago,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'phone');
    final phone = LocalWalSyncImpl(_Listener(), uploadGate: _offlineGate(), persistWals: (_) async {});
    // A live-session retry calls phone.syncWal directly, outside WalSyncs.
    final uploading = waitingWal(600)..isSyncing = true;
    final idle = waitingWal(540);
    phone.testWals = [uploading, idle];
    final syncs = WalSyncs(_Listener(), phoneSync: phone, ringSync: _Ring());
    final provider = SyncProvider(walService: _Service(syncs), uploadGate: _offlineGate(), startBackgroundSync: false);
    addTearDown(provider.dispose);
    await provider.initialized;

    final outcome = await provider.clearStorage(
      StorageClearScope.notUploaded,
      settleTimeout: const Duration(milliseconds: 200),
    );
    expect(outcome.failed, isTrue);
    expect(phone.testWals, containsAll([uploading, idle]), reason: 'nothing is deleted while an upload runs');

    // Even inside a clear, the bulk delete never removes a recording mid-upload.
    await phone.deleteAllPendingWals(includeAccepted: false);
    expect(phone.testWals, [uploading]);
  });

  test('a transfer that will not stop in time aborts the clear and deletes nothing', () async {
    if (!ringDrainRecoveryEnabled) return;
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final phone = LocalWalSyncImpl(_Listener(), uploadGate: _offlineGate(), persistWals: (_) async {});
    final waiting = Wal(
        timerStart: now - 600,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'phone');
    phone.testWals = [waiting];
    final ring = _StuckRing();
    final syncs = WalSyncs(_Listener(), phoneSync: phone, ringSync: ring);
    syncs.setDevice(BtDevice(id: 'pendant', name: 'Omi', type: DeviceType.omi, rssi: -40), firmwareVersion: '3.0.21');
    syncs.configureRingDrain(() => true);
    await _settle();
    final provider = SyncProvider(walService: _Service(syncs), uploadGate: _offlineGate(), startBackgroundSync: false);
    addTearDown(() {
      ring.release();
      syncs.disableRingDrain();
      provider.dispose();
    });
    await provider.initialized;

    final outcome =
        await provider.clearStorage(StorageClearScope.notUploaded, settleTimeout: const Duration(milliseconds: 300));

    expect(outcome.failed, isTrue);
    expect(outcome.deletedSeconds, 0);
    expect(ring.events, isEmpty, reason: 'no clear was sent while the read was still running');
    expect(provider.allWals, contains(waiting));
    expect(syncs.transfersHeldForClear, isFalse);
  });
}

/// A reader that ignores cancellation, as a wedged BLE read would.
class _StuckRing extends _Ring {
  @override
  void cancelSync() {}
  void release() => finishRead();
}
