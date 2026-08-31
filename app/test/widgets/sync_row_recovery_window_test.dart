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
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

/// A recording the server permanently refused for being older than the
/// automatic-recovery window must say so on its row, and must not offer a
/// Retry that can never succeed (#10975).

class _Listener implements IWalSyncListener {
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}

  @override
  void onWalUpdated() {}
}

class _LocalSyncs {
  _LocalSyncs(this.phone);

  final LocalWalSyncImpl phone;

  Future<List<Wal>> getAllWals() => phone.getAllWals();
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

  @override
  noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

SyncUploadGate _offlineGate() => SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
        throw StateError('unexpected upload in a widget test');
      },
      fairUseStatusLoader: () async => {'stage': 'none'},
    );

Widget _app(Widget child, SyncProvider provider) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: ChangeNotifierProvider<SyncProvider>.value(
      value: provider,
      child: Scaffold(backgroundColor: Colors.black, body: child),
    ),
  );
}

void main() {
  late Directory tempDir;
  late LocalWalSyncImpl localSync;
  SyncProvider? provider;

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    tempDir = await Directory.systemTemp.createTemp('sync_row_recovery_window_');
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

  Future<SyncProvider> pumpRow(WidgetTester tester, Wal wal) async {
    localSync.testWals = [wal];
    final syncProvider = SyncProvider(
      walService: _WalService(_LocalSyncs(localSync)),
      uploadGate: _offlineGate(),
      startBackgroundSync: false,
    );
    provider = syncProvider;
    await syncProvider.initialized;
    await tester.pumpWidget(
      _app(
        WalListItem(wal: wal, date: DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000), walIdx: 0),
        syncProvider,
      ),
    );
    await tester.pump();
    return syncProvider;
  }

  Wal makeWal(WalStatus status) => Wal(
        timerStart: 1700000000,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: status,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'too_old_audio.bin',
      );

  testWidgets('the row explains the rejection and offers no Retry', (tester) async {
    await pumpRow(tester, makeWal(WalStatus.outsideRecoveryWindow));

    expect(find.text("Too old to sync — Omi can't accept it"), findsOneWidget);
    expect(find.text('Retry'), findsNothing);
    expect(find.text('Waiting to sync'), findsNothing);
  });

  testWidgets('a still-retryable recording keeps its Retry affordance', (tester) async {
    await pumpRow(tester, makeWal(WalStatus.miss)..retryCount = walMaxAutoRetries);

    expect(find.text('Failed — tap Retry'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });
}
