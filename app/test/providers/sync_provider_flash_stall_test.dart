import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Regression coverage for the silent-success bug: a Limitless flash-page
/// drain that stalls because the pendant is actively recording used to fall
/// through to `toCompleted`, telling the user everything synced when nothing
/// did. The provider must surface an error state explaining that the pendant
/// needs to stop recording first.
class _FakeSyncs {
  FlashSyncStallReason flashStallReason = FlashSyncStallReason.none;
  SyncLocalFilesResponse? syncAllResult;
  Object? syncAllError;

  Future<List<Wal>> getAllWals() async => [];

  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    final error = syncAllError;
    if (error != null) throw error;
    return syncAllResult;
  }
}

class _FakeWalService implements IWalService {
  final _FakeSyncs syncs = _FakeSyncs();

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
  });

  test('flash drain stalled by an actively recording pendant surfaces an error, not silent success', () async {
    final walService = _FakeWalService();
    walService.syncs.flashStallReason = FlashSyncStallReason.recordingSuspected;

    final provider = SyncProvider(walService: walService, uploadGate: _hermeticGate(), startBackgroundSync: false);
    await provider.initialized;

    await provider.syncWals();

    expect(provider.syncState.hasError, isTrue, reason: 'stall while recording must not report success');
    expect(provider.syncError, isNotNull);
    expect(provider.syncError!.toLowerCase(), contains('recording'));
    provider.dispose();
  });

  test('flash drain stalled by a full pendant surfaces an error, not silent success', () async {
    final walService = _FakeWalService();
    walService.syncs.flashStallReason = FlashSyncStallReason.deviceFull;

    final provider = SyncProvider(walService: walService, uploadGate: _hermeticGate(), startBackgroundSync: false);
    await provider.initialized;

    await provider.syncWals();

    expect(provider.syncState.hasError, isTrue, reason: 'stall on a full pendant must not report success');
    expect(provider.syncError, isNotNull);
    expect(provider.syncError!.toLowerCase(), contains('full'));
    provider.dispose();
  });

  test('flash sync with no stall and no new conversations still completes normally', () async {
    final walService = _FakeWalService();
    walService.syncs.flashStallReason = FlashSyncStallReason.none;

    final provider = SyncProvider(walService: walService, uploadGate: _hermeticGate(), startBackgroundSync: false);
    await provider.initialized;

    await provider.syncWals();

    expect(provider.syncState.isCompleted, isTrue);
    expect(provider.syncState.hasError, isFalse);
    provider.dispose();
  });

  test('an unknown flash stall surfaces an error instead of silent success', () async {
    final walService = _FakeWalService();
    walService.syncs.flashStallReason = FlashSyncStallReason.unknown;

    final provider = SyncProvider(walService: walService, uploadGate: _hermeticGate(), startBackgroundSync: false);
    await provider.initialized;

    await provider.syncWals();

    expect(provider.syncState.hasError, isTrue);
    expect(provider.syncError,
        "Your Pendant's stored audio could not be confirmed. Keep your Pendant connected and try syncing again.");
    provider.dispose();
  });

  test('an incomplete per-recording flash transfer surfaces the localized stall reason', () async {
    final walService = _FakeWalService();
    walService.syncs
      ..flashStallReason = FlashSyncStallReason.unknown
      ..syncAllError = StateError('Device transfer incomplete; recording kept on device');

    final provider = SyncProvider(walService: walService, uploadGate: _hermeticGate(), startBackgroundSync: false);
    await provider.initialized;

    await provider.syncWals();

    expect(provider.syncState.hasError, isTrue);
    expect(provider.syncError,
        "Your Pendant's stored audio could not be confirmed. Keep your Pendant connected and try syncing again.");
    provider.dispose();
  });
}
