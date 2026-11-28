import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/services/wals/storage_clear.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_derived_sync_views.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/pages/conversations/widgets/sync_details_sheet.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/sfpro_font_fixtures.dart';

class _Sync extends ChangeNotifier with WalDerivedSyncViews implements SyncProvider {
  _Sync(this.wals, {this.state = const SyncState()});
  final SyncState state;
  final List<Wal> wals;
  @override
  SyncState get syncState => state;
  @override
  bool get isRateLimited => false;
  @override
  bool get isSyncing => state.isSyncing;
  @override
  ({int processed, int total}) get offlineServerProcessingCounts => (processed: 0, total: 0);
  @override
  String? get syncError => null;
  @override
  Wal? get failedWal => null;
  @override
  bool get isLoadingWals => false;
  @override
  List<Wal> get allWals => wals;
  @override
  List<Wal> get uploadedWals => wals.where((w) => w.status == WalStatus.uploaded).toList();
  @override
  List<Wal> get missingWals => wals.where((w) => w.status == WalStatus.miss).toList();
  @override
  int get missingWalsInSeconds => missingWals.fold(0, (sum, wal) => sum + wal.seconds);
  @override
  ({int doneSeconds, int totalSeconds, bool tracked}) get offlineServerProcessingSeconds =>
      (doneSeconds: 0, totalSeconds: uploadedWals.fold(0, (sum, wal) => sum + wal.seconds), tracked: true);
  @override
  List<Wal> get displaySortedWals => wals;
  @override
  int get needsAttentionWalsCount => wals.where((w) => w.status == WalStatus.corrupted).length;
  @override
  StorageAmounts get storageAmounts => StorageAmounts.of(const []);
  @override
  bool get syncCompleted => false;
  @override
  WalStatusFilter get statusFilter => WalStatusFilter.pending;
  @override
  int get pendingStatusCount => missingWals.length + uploadedWals.length;
  @override
  int get syncedStatusCount => wals.where((w) => w.status == WalStatus.synced).length;
  @override
  int get corruptedStatusCount => needsAttentionWalsCount;
  @override
  List<Wal> get filteredByStatusWals => [...missingWals, ...uploadedWals];
  @override
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) =>
      filter == WalDisplayFilter.pending ? wals.where((w) => w.status != WalStatus.synced).toList() : wals;
  @override
  Future<void> refreshWals() async {}
  @override
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  String get currentFirmwareVersion => 'Unknown';
  @override
  bool get isConnected => true;
  @override
  Future<void> refreshRingStorageStatus() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _User extends ChangeNotifier implements UserProvider {
  @override
  bool get privateCloudSyncEnabled => false;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _pump(WidgetTester tester, Widget page, WalStatus status,
    {List<Wal>? recordings, SyncState state = const SyncState()}) async {
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final sync = _Sync(
      recordings ??
          [
            Wal(
                timerStart: 1790730000,
                codec: BleAudioCodec.opus,
                seconds: 30,
                status: status,
                storage: WalStorage.disk,
                device: 'phone')
          ],
      state: state);
  final device = _Device(), user = _User();
  addTearDown(sync.dispose);
  addTearDown(device.dispose);
  addTearDown(user.dispose);
  final previous = OmiColors.active;
  OmiColors.active = OmiPalette.dark;
  addTearDown(() => OmiColors.active = previous);
  {
    await tester.runAsync(() async {
      for (final entry in jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>) {
        final loader = FontLoader(entry['family'] as String);
        for (final font in entry['fonts'] as List<dynamic>) {
          loader.addFont(rootBundle.load(font['asset'] as String));
        }
        await loader.load();
      }

      for (final family in [
        'SF Pro Display',
        '.SF UI Text',
        '.SF UI Display',
        '.SF Pro Text',
        '.SF Pro Display',
        'CupertinoSystemText',
        'CupertinoSystemDisplay',
        'FlutterTest',
        'Roboto'
      ]) {
        final loader = FontLoader(family);
        loader.addFont(sfProFont('SFPRODISPLAYREGULAR.OTF'));
        loader.addFont(sfProFont('SFPRODISPLAYMEDIUM.OTF'));
        await loader.load();
      }
    });
  }
  final baseTheme = buildOmiTheme();
  final theme = baseTheme.copyWith(
    platform: TargetPlatform.iOS,
    textTheme: baseTheme.textTheme.apply(fontFamily: 'SF Pro Display'),
    primaryTextTheme: baseTheme.primaryTextTheme.apply(fontFamily: 'SF Pro Display'),
    appBarTheme: baseTheme.appBarTheme
        .copyWith(titleTextStyle: baseTheme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display')),
  );
  await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<SyncProvider>.value(value: sync),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<UserProvider>.value(value: user),
      ],
      child: RepaintBoundary(
          key: const ValueKey('sync-completion-evidence'),
          child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            theme: theme,
            debugShowCheckedModeBanner: false,
            home: page,
          ))));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
}

Future<void> _capture(WidgetTester tester, String name) async {
  const evidence = String.fromEnvironment('OMI_SYNC_UI_EVIDENCE_DIR');
  if (evidence.isEmpty) return;
  await tester.runAsync(() async {
    final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(const ValueKey('sync-completion-evidence')));
    final image = await boundary.toImage(pixelRatio: 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    final dir = await Directory(evidence).create(recursive: true);
    await File('${dir.path}/$name').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

void main() {
  final now = DateTime.now();
  List<Wal> rows() {
    Wal row(int ago, int seconds, WalStatus status, {WalStorage storage = WalStorage.disk}) => Wal(
          timerStart: now.subtract(Duration(seconds: ago)).millisecondsSinceEpoch ~/ 1000,
          codec: BleAudioCodec.opus,
          seconds: seconds,
          status: status,
          storage: storage,
          device: 'synthetic',
          uploadedAt: now.millisecondsSinceEpoch ~/ 1000,
        );
    return [
      row(600, 74, WalStatus.miss, storage: WalStorage.sdcard),
      row(1800, 960, WalStatus.miss),
      row(86400, 120, WalStatus.uploaded),
      row(40 * 86400, 3600, WalStatus.uploaded)..uploadedAt = 0,
    ];
  }

  testWidgets('On the Way separates pending audio stalled uploads and server-only work', (tester) async {
    final store = PendingWorkStore(
        loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
        loadPending: () async => ApiSuccess(PendingWorkSnapshot(enabled: true, attentionUnseenCount: 0, items: [
              PendingWorkItem(
                id: 'synthetic-server',
                kind: 'recording',
                state: 'transcribing',
                conversationIds: const [],
                startedAt: now.subtract(const Duration(days: 2)),
                durationSeconds: 720,
              )
            ])));
    addTearDown(store.dispose);
    await store.refresh();
    await _pump(tester, OnTheWayPage(clock: () => now, pendingWork: store, multiFileSync: true), WalStatus.uploaded,
        recordings: rows());
    expect(find.text('Uploaded, awaiting server'), findsWidgets);
    expect(find.text('Your audio is safe on your device or phone'), findsOneWidget);
    expect(find.text('Server-reported work'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await _capture(tester, '001-mobile-ios-pending-work-truth.png');
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('Sync details counts only active folded pending audio', (tester) async {
    final sync = _Sync(rows()), device = _Device();
    addTearDown(sync.dispose);
    addTearDown(device.dispose);
    await _pump(
        tester,
        Scaffold(
            appBar: AppBar(title: const Text('Sync details')),
            body: SyncDetailsSheet(sync: sync, device: device, onHowSyncingWorks: () {})),
        WalStatus.uploaded);
    expect(find.text('Uploaded, awaiting server'), findsOneWidget);
    expect(find.text('2m'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await _capture(tester, '002-mobile-ios-sync-details-truth.png');
  });

  testWidgets('Offline Sync banner includes active server waits in its audio total', (tester) async {
    await _pump(tester, const AutoSyncPage(), WalStatus.uploaded,
        recordings: rows(), state: const SyncState(status: SyncStatus.syncing, phase: SyncPhase.downloadingFromDevice));
    expect(find.text('Syncing 19m of audio'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await _capture(tester, '003-mobile-ios-sync-banner-truth.png');
  });
}
