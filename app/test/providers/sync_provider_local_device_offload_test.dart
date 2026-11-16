import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A narrow fake for the local-only route. `getSyncs()` is deliberately
/// dynamic in [IWalService], so this exposes only the members the provider
/// must use while draining a Pendant without cloud sync.
class _FakeSyncs {
  final List<Wal> wals = [];
  int localDeviceOffloadCalls = 0;
  int genericSyncAllCalls = 0;
  bool isStorageSyncing = false;
  bool isSdCardSyncing = false;
  FlashSyncStallReason flashStallReason = FlashSyncStallReason.none;

  Future<List<Wal>> getAllWals() async => List<Wal>.of(wals);

  Future<SyncLocalFilesResponse?> syncDeviceWalsToPhone({IWalSyncProgressListener? progress}) async {
    localDeviceOffloadCalls++;
    progress?.onWalSyncedProgress(0.0, phase: SyncPhase.downloadingFromDevice);
    for (final wal in wals.where((wal) => wal.status == WalStatus.miss)) {
      wal.status = WalStatus.synced;
    }
    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    genericSyncAllCalls++;
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

SyncUploadGate _hermeticGate() {
  final limiter = SyncRateLimiter.instance;
  limiter.clear();
  return SyncUploadGate(
    limiter: limiter,
    fairUseStatusLoader: () async => {'stage': 'none'},
    uploader: (files,
            {onUploadProgress,
            conversationId,
            captureEvidence,
            recordingSessionId,
            audioStartSeconds,
            audioEndSeconds,
            claimLiveCapture = false,
            geolocation}) async =>
        UploadFilesResult.queued('unused'),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
  });

  test('custom-STT device offload drains Pendant pages locally without generic cloud sync', () async {
    final syncs = _FakeSyncs()
      ..wals.add(
        Wal(
          timerStart: 1000,
          codec: BleAudioCodec.pcm16,
          seconds: 120,
          storage: WalStorage.flashPage,
          status: WalStatus.miss,
        ),
      );
    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      uploadGate: _hermeticGate(),
      startBackgroundSync: false,
    );
    await provider.initialized;

    await provider.drainDeviceWalsToPhone();

    expect(syncs.localDeviceOffloadCalls, 1);
    expect(syncs.genericSyncAllCalls, 0, reason: 'local offload must never take the cloud-sync route');
    expect(syncs.wals.single.status, WalStatus.synced);
    expect(provider.syncState.isCompleted, isTrue);
    provider.dispose();
  });

  test('a full Pendant still surfaces an actionable local-offload error', () async {
    final syncs = _FakeSyncs()..flashStallReason = FlashSyncStallReason.deviceFull;
    final provider = SyncProvider(
      walService: _FakeWalService(syncs),
      uploadGate: _hermeticGate(),
      startBackgroundSync: false,
    );
    await provider.initialized;

    await provider.drainDeviceWalsToPhone();

    expect(syncs.localDeviceOffloadCalls, 1);
    expect(syncs.genericSyncAllCalls, 0);
    expect(provider.syncState.hasError, isTrue);
    expect(provider.syncError!.toLowerCase(), contains('full'));
    provider.dispose();
  });
}
