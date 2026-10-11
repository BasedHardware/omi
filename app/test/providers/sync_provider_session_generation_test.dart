import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeSyncs {
  final List<Wal> wals;
  Completer<SyncLocalFilesResponse?>? hangSyncWal;
  Completer<List<Wal>>? hangGetAllWals;
  int getAllWalsCalls = 0;
  int cancelSyncCalls = 0;

  _FakeSyncs(this.wals);

  Future<List<Wal>> getAllWals() async {
    getAllWalsCalls++;
    final hang = hangGetAllWals;
    if (hang != null) return hang.future;
    return List<Wal>.of(wals);
  }

  Future<void> refreshWalsFromDevice({String? firmwareVersion}) async {}

  bool get isStorageSyncing => false;
  bool get isSdCardSyncing => false;

  SyncLocalFilesResponse? get accumulatedResponse => null;

  void cancelSync() {
    cancelSyncCalls++;
  }

  void clearUserData() {
    cancelSync();
  }

  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    final hang = hangSyncWal;
    if (hang != null) return hang.future;
    wal.status = WalStatus.uploaded;
    wal.jobId = 'job-202';
    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
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

Wal _wal() => Wal(timerStart: 1000, codec: BleAudioCodec.pcm16, seconds: 30, status: WalStatus.miss);

Future<SyncProvider> _provider(_FakeSyncs syncs) async {
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  SyncRateLimiter.instance.clear();
  final provider = SyncProvider(walService: _FakeWalService(syncs), startBackgroundSync: false);
  await provider.initialized;
  return provider;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('clearUserData mid-sync refuses to publish the stale WAL list or job cache', () async {
    final wal = _wal();
    final syncs = _FakeSyncs([wal]);
    syncs.hangSyncWal = Completer<SyncLocalFilesResponse?>();
    final provider = await _provider(syncs);
    addTearDown(provider.dispose);

    expect(provider.allWals, isNotEmpty);

    final sync = provider.syncWal(wal);
    provider.clearUserData();
    expect(provider.allWals, isEmpty);
    expect(provider.syncState.isIdle, isTrue);
    expect(syncs.cancelSyncCalls, 1);

    wal.status = WalStatus.uploaded;
    wal.jobId = 'job-202';
    syncs.hangSyncWal!.complete(SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []));
    await sync;

    expect(provider.allWals, isEmpty, reason: 'finally must not recapture and reload the previous session');
    expect(provider.syncState.isIdle, isTrue);
    expect(provider.syncState.hasError, isFalse);
    expect(provider.syncState.isCompleted, isFalse);
    expect(provider.offlineServerProcessingCounts.total, 0);
  });

  test('clearUserData mid-refreshWals discards the hung list', () async {
    final syncs = _FakeSyncs([_wal()]);
    final provider = await _provider(syncs);
    addTearDown(provider.dispose);

    syncs.hangGetAllWals = Completer<List<Wal>>();
    final refresh = provider.refreshWals();
    provider.clearUserData();
    syncs.hangGetAllWals!.complete([_wal()..status = WalStatus.synced]);
    await refresh;

    expect(provider.allWals, isEmpty);
    expect(provider.isLoadingWals, isFalse);
  });

  test('a current-generation refresh after clearUserData still loads', () async {
    final wal = _wal();
    final syncs = _FakeSyncs([wal]);
    final provider = await _provider(syncs);
    addTearDown(provider.dispose);

    provider.clearUserData();
    expect(provider.allWals, isEmpty);

    await provider.refreshWals();
    expect(provider.allWals, [wal]);
  });
}
