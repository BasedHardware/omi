import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/devices/connectors/limitless_connection.dart';
import 'package:omi/services/wals/flash_page_wal_sync.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Regression coverage for the silent-success bug: a Limitless flash-page
/// drain that stalls because the pendant is actively recording used to fall
/// through to `toCompleted`, telling the user everything synced when nothing
/// did. The provider must surface an error state explaining that the pendant
/// needs to stop recording first.
class _FakeSyncs {
  _FakeSyncs({this.flashSync});

  final FlashPageWalSyncImpl? flashSync;
  FlashSyncStallReason _flashStallReason = FlashSyncStallReason.none;
  FlashSyncStallReason get flashStallReason => flashSync?.lastStallReason ?? _flashStallReason;
  set flashStallReason(FlashSyncStallReason reason) => _flashStallReason = reason;
  SyncLocalFilesResponse? syncAllResult;
  Object? syncAllError;

  Future<List<Wal>> getAllWals() async {
    final flash = flashSync;
    if (flash == null) return [];
    return flash.getMissingWals();
  }

  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    final error = syncAllError;
    if (error != null) throw error;
    final flash = flashSync;
    if (flash != null) {
      await flash.refreshWalsFromDevice();
      await flash.syncAll(progress: progress);
    }
    return syncAllResult;
  }
}

class _FakeWalService implements IWalService {
  _FakeWalService([_FakeSyncs? syncs]) : syncs = syncs ?? _FakeSyncs();

  final _FakeSyncs syncs;

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

class _FakeFlashLimitless implements LimitlessDeviceConnection {
  _FakeFlashLimitless({required this.storageStatus, this.unavailableCalls = const {}});

  final Map<String, int> storageStatus;
  final Set<int> unavailableCalls;
  int statusCalls = 0;

  @override
  Future<Map<String, int>?> getStorageStatus() async {
    statusCalls++;
    if (unavailableCalls.contains(statusCalls)) return null;
    return Map.of(storageStatus);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _NoopSyncListener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
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

  test('a failed flash status read reaches SyncProvider and a later success clears it', () async {
    final pendant = _FakeFlashLimitless(
      storageStatus: {'oldest_flash_page': 1, 'newest_flash_page': 0, 'free_capture_pages': 12},
      unavailableCalls: {1},
    );
    final flashSync = FlashPageWalSyncImpl(_NoopSyncListener())
      ..testDevice = BtDevice(name: 'Limitless Pendant', id: 'limitless-1', type: DeviceType.limitless, rssi: -40)
      ..testConnection = pendant;
    final walService = _FakeWalService(_FakeSyncs(flashSync: flashSync));
    final provider = SyncProvider(walService: walService, uploadGate: _hermeticGate(), startBackgroundSync: false);
    await provider.initialized;

    await provider.syncWals();

    expect(pendant.statusCalls, 1);
    expect(provider.syncError,
        "Your Pendant's stored audio could not be confirmed. Keep your Pendant connected and try syncing again.");

    await provider.syncWals();

    expect(pendant.statusCalls, 2);
    expect(provider.syncState.isCompleted, isTrue);
    expect(provider.syncError, isNull);
    provider.dispose();
  });

  testWidgets('an unknown flash stall uses the localized pendant message', (tester) async {
    final walService = _FakeWalService();
    walService.syncs.flashStallReason = FlashSyncStallReason.unknown;
    final provider = SyncProvider(walService: walService, uploadGate: _hermeticGate(), startBackgroundSync: false);
    await provider.initialized;

    await tester.pumpWidget(MaterialApp(
      navigatorKey: globalNavigatorKey,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: const Scaffold(),
    ));
    final localizedMessage =
        AppLocalizations.of(globalNavigatorKey.currentContext!)!.pendantAudioUnconfirmedSyncBlocked;

    await provider.syncWals();

    expect(provider.syncError, localizedMessage);
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
