import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations_en.dart';
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
  Object? nextError;

  _FakeSyncs(this.wals);

  Future<List<Wal>> getAllWals() async => List<Wal>.of(wals);

  Future<void> refreshWalsFromDevice({String? firmwareVersion}) async {}

  bool get isStorageSyncing => false;
  bool get isSdCardSyncing => false;

  SyncLocalFilesResponse? get accumulatedResponse => null;

  void cancelSync() {}

  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    syncWalCalls++;
    if (nextError case final error?) throw error;
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

  test('partial localUploadFailures re-arm recovery without SyncStatus.error', () async {
    // Regression #4587: leave/background aborts paint as localUploadFailures;
    // schema says those WALs stay miss and must soft-retry, not red-error.
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

    expect(provider.syncState.hasError, isFalse);
    expect(provider.syncState.isIdle, isTrue);
    expect(wal.status, WalStatus.miss);
    expect(
        wakes,
        [
          WakeTrigger.cooldownElapsed,
        ],
        reason: 'transient localUploadFailures must emit exactly one re-arm wake from _performSync');
    provider.dispose();
  });

  test('permanent localUploadFailures still surface SyncStatus.error', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final wal = Wal(timerStart: 1000, codec: BleAudioCodec.pcm16, seconds: 30, status: WalStatus.miss);
    final syncs = _FakeSyncs([wal])
      ..nextSyncResult = SyncLocalFilesResponse(
        newConversationIds: [],
        updatedConversationIds: [],
        localUploadFailures: 1,
        localUploadPermanentFailures: 1,
        localUploadPermanentError: 'Exception: Audio file could not be processed by server',
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
    expect(provider.syncError, isNot(contains('connection')));
    expect(wakes, isEmpty, reason: 'permanent refusals must not soft-retry via cooldown wake');
    provider.dispose();
  });

  test('server upload failure keeps its retry classification without blaming connectivity', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final wal = Wal(timerStart: 1000, codec: BleAudioCodec.pcm16, seconds: 30, status: WalStatus.miss);
    final syncs = _FakeSyncs([wal])..nextError = Exception('Server is temporarily unavailable');
    final provider = SyncProvider(walService: _FakeWalService(syncs), startBackgroundSync: false);
    await provider.initialized;

    await provider.syncWal(wal);

    expect(provider.syncError, contains('Server is temporarily unavailable'));
    expect(provider.syncError, contains('phone audio file'));
    expect(provider.syncError, isNot(contains('connection')));
    provider.dispose();
  });

  test('generic upload failure uses a locale-neutral code with terminal localized failure copy', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final wal = Wal(timerStart: 1000, codec: BleAudioCodec.pcm16, seconds: 30, status: WalStatus.miss);
    final syncs = _FakeSyncs([wal])..nextError = Exception('Upload failed unexpectedly');
    final provider = SyncProvider(walService: _FakeWalService(syncs), startBackgroundSync: false);
    await provider.initialized;

    await provider.syncWal(wal);

    expect(provider.syncError, SyncProvider.pendingUploadErrorCode);
    expect(SyncProvider.isPendingUploadError(provider.syncError), isTrue);
    // The pages own this mapping so a provider state never ships English. The
    // terminal error card has an explicit Retry action; it must not claim that
    // an automatic retry is already in progress.
    final localizedFailure = AppLocalizationsEn().syncStatusFailed;
    expect(localizedFailure, contains('Failed'));
    expect(localizedFailure, isNot(contains('retrying')));
    expect(provider.syncError, isNot(contains('connection')));
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
}
