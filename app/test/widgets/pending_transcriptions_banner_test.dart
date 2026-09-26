import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/pending_transcriptions_banner.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _LocalSyncs {
  _LocalSyncs(this.phone);

  final LocalWalSyncImpl phone;

  Future<List<Wal>> getAllWals() => phone.getAllWals();

  Future<void> deleteAllSyncedWals() => phone.deleteAllSyncedWals();

  Future<void> deleteAllPendingWals() => phone.deleteAllPendingWals();

  Future<void> deleteAllCorruptedWals() => phone.deleteAllCorruptedWals();
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

SyncUploadGate _offlineGate() {
  return SyncUploadGate(
    limiter: SyncRateLimiter.instance,
    uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
      throw StateError('unexpected upload in banner test');
    },
    fairUseStatusLoader: () async => {'stage': 'none'},
  );
}

Wal _wal({required int timerStart, WalStatus status = WalStatus.miss, WalStorage storage = WalStorage.disk}) {
  return Wal(
    timerStart: timerStart,
    codec: BleAudioCodec.opus,
    seconds: 60,
    status: status,
    storage: storage,
    device: 'omi',
    filePath: 'banner_$timerStart.bin',
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

    tempDir = await Directory.systemTemp.createTemp('pending_banner_');
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

  Future<SyncProvider> makeProvider() async {
    final syncProvider = SyncProvider(
      walService: _WalService(_LocalSyncs(localSync)),
      uploadGate: _offlineGate(),
      startBackgroundSync: false,
    );
    provider = syncProvider;
    await syncProvider.initialized;
    return syncProvider;
  }

  Future<void> pumpBanner(WidgetTester tester, SyncProvider syncProvider) async {
    await tester.pumpWidget(
      MaterialApp(
        locale: const Locale('en'),
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: ChangeNotifierProvider<SyncProvider>.value(
              value: syncProvider, child: const PendingTranscriptionsBanner()),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('shows the pending count while phone-local recordings wait to upload', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    localSync.testWals = [
      _wal(timerStart: now - 120, status: WalStatus.miss),
      _wal(timerStart: now - 60, status: WalStatus.miss),
      _wal(timerStart: now - 30, status: WalStatus.uploaded),
    ];
    final syncProvider = await makeProvider();

    expect(syncProvider.pendingLocalTranscriptionWals.length, 3,
        reason: 'uploaded counts as pending until the server job finishes');

    await pumpBanner(tester, syncProvider);

    expect(find.byKey(const Key('pending_transcriptions_banner')), findsOneWidget);
    expect(find.text('Transcriptions pending 3'), findsOneWidget);
  });

  testWidgets('hides when the backlog is only synced or device-side recordings', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    localSync.testWals = [
      _wal(timerStart: now - 120, status: WalStatus.synced),
      _wal(timerStart: now - 60, status: WalStatus.miss, storage: WalStorage.sdcard),
      _wal(timerStart: now - 30, status: WalStatus.miss, storage: WalStorage.flashPage),
    ];
    final syncProvider = await makeProvider();

    expect(syncProvider.pendingLocalTranscriptionWals, isEmpty,
        reason: 'device-side files drain through the sync pages, not this backlog');

    await pumpBanner(tester, syncProvider);

    expect(find.byKey(const Key('pending_transcriptions_banner')), findsNothing);
  });
}
