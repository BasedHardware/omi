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
import 'package:omi/pages/home/widgets/header_sync_button.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/ui/ui.dart';
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
    uploader: (
      files, {
      onUploadProgress,
      conversationId,
      captureEvidence,
      recordingSessionId,
      audioStartSeconds,
      audioEndSeconds,
      claimLiveCapture = false,
      geolocation,
    }) async {
      throw StateError('unexpected upload in sync button test');
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
    filePath: 'sync_button_$timerStart.bin',
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

    tempDir = await Directory.systemTemp.createTemp('header_sync_button_');
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

  Future<void> pumpButton(WidgetTester tester, SyncProvider syncProvider, {bool hasPairedDevice = false}) async {
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
          body: Center(
            child: ChangeNotifierProvider<SyncProvider>.value(
              value: syncProvider,
              child: HeaderSyncButton(hasPairedDevice: hasPairedDevice, onTap: () {}),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('badges the count while phone-local recordings wait, even with no device paired', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    localSync.testWals = [
      _wal(timerStart: now - 120, status: WalStatus.miss),
      _wal(timerStart: now - 60, status: WalStatus.miss),
      _wal(timerStart: now - 30, status: WalStatus.uploaded),
    ];
    final syncProvider = await makeProvider();

    expect(
      syncProvider.pendingLocalTranscriptionWals.length,
      3,
      reason: 'uploaded counts as pending until the server job finishes',
    );

    final semantics = tester.ensureSemantics();
    await pumpButton(tester, syncProvider);

    expect(find.byKey(const ValueKey('header_sync_button')), findsOneWidget);
    expect(find.byKey(const ValueKey('header_count_badge')), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    expect(find.bySemanticsLabel('Sync, Transcriptions pending 3'), findsOneWidget);
    semantics.dispose();
  });

  testWidgets('caps the badge at 9+', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    localSync.testWals = [for (var i = 0; i < 12; i++) _wal(timerStart: now - 600 + i * 30)];
    final syncProvider = await makeProvider();

    await pumpButton(tester, syncProvider);

    expect(find.text('9+'), findsOneWidget);
  });

  testWidgets('shows no badge when nothing waits, and hides without a paired device', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    localSync.testWals = [_wal(timerStart: now - 120, status: WalStatus.synced)];
    final syncProvider = await makeProvider();

    await pumpButton(tester, syncProvider, hasPairedDevice: true);
    expect(find.byKey(const ValueKey('header_sync_button')), findsOneWidget);
    expect(find.byKey(const ValueKey('header_count_badge')), findsNothing);

    await pumpButton(tester, syncProvider);
    expect(find.byKey(const ValueKey('header_sync_button')), findsNothing);
  });

  testWidgets('stays quiet: no fill, muted badge, and no warning colour even when files wait on the device',
      (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    localSync.testWals = [_wal(timerStart: now - 120, storage: WalStorage.sdcard)];
    final syncProvider = await makeProvider();
    expect(syncProvider.missingWalsOnDevice, isNotEmpty);

    await pumpButton(tester, syncProvider, hasPairedDevice: true);

    final count = tester.widget<Text>(find.byKey(const ValueKey('header_count_badge')));
    expect(count.style!.color, OmiColors.textTertiary);

    final icon = tester.widget<Icon>(
      find.descendant(of: find.byKey(const ValueKey('header_sync_button')), matching: find.byType(Icon)),
    );
    expect(icon.color, OmiColors.textTertiary);
    expect(
        find.byWidgetPredicate((w) =>
            w is Container &&
            w.decoration is BoxDecoration &&
            (w.decoration as BoxDecoration).color == OmiColors.warning),
        findsNothing);
  });
}
