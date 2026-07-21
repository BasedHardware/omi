import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/sync_provider.dart';
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
  SyncLocalFilesResponse? nextSyncResult;
  Completer<SyncLocalFilesResponse?>? hangSyncWal;

  _FakeSyncs(this.wals);

  Future<List<Wal>> getAllWals() async => List<Wal>.of(wals);

  Future<void> refreshWalsFromDevice({String? firmwareVersion}) async {}

  bool get isStorageSyncing => false;
  bool get isSdCardSyncing => false;

  SyncLocalFilesResponse? get accumulatedResponse => null;

  void cancelSync() {}

  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    syncWalCalls++;
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

  test('syncWal during an in-flight sync wakes the coordinator instead of racing', () async {
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

    await provider.syncWal(other);

    expect(syncs.syncWalCalls, 1, reason: 'contended syncWal must not start a parallel upload');
    expect(wakes, [WakeTrigger.userRetry]);

    hang.complete(SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []));
    await first;
    provider.dispose();
  });
}
