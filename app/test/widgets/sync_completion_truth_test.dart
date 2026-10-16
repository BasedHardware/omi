import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';

class _Sync extends ChangeNotifier implements SyncProvider {
  _Sync(this.wals);
  final List<Wal> wals;
  @override
  SyncState get syncState => const SyncState();
  @override
  bool get isRateLimited => false;
  @override
  bool get isSyncing => false;
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
  int get clearableWalsCount => 0;
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

Future<void> _pump(WidgetTester tester, Widget page, WalStatus status, {List<Wal>? recordings}) async {
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final sync = _Sync(recordings ??
      [
        Wal(
            timerStart: 1790730000,
            codec: BleAudioCodec.opus,
            seconds: 30,
            status: status,
            storage: WalStorage.disk,
            device: 'phone')
      ]);
  final device = _Device(), user = _User();
  addTearDown(sync.dispose);
  addTearDown(device.dispose);
  addTearDown(user.dispose);
  final previous = OmiColors.active;
  OmiColors.active = OmiPalette.dark;
  addTearDown(() => OmiColors.active = previous);
  const evidence = String.fromEnvironment('OMI_SYNC_UI_EVIDENCE_DIR');
  if (evidence.isNotEmpty) {
    await tester.runAsync(() async {
      for (final entry in jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>) {
        final loader = FontLoader(entry['family'] as String);
        for (final font in entry['fonts'] as List<dynamic>) {
          loader.addFont(rootBundle.load(font['asset'] as String));
        }
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
  if (status == WalStatus.uploaded) {
    // An indeterminate processing spinner is expected until the server settles.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
  } else {
    await tester.pumpAndSettle();
  }
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
  testWidgets('legacy Offline Sync never claims completion while a recording needs attention', (tester) async {
    await _pump(tester, const SyncPage(), WalStatus.corrupted);
    expect(find.text('1 recording need attention'), findsOneWidget);
    expect(find.text('All recordings synced'), findsNothing);
    expect(find.text('All caught up'), findsNothing);
    expect(tester.takeException(), isNull);
    await _capture(tester, '003-mobile-ios-sync-needs-attention.png');
  });

  testWidgets('Auto Sync reports processing without inventing a conversation result', (tester) async {
    await _pump(tester, const AutoSyncPage(), WalStatus.synced);
    await tester.tap(find.text('Synced'));
    await tester.pumpAndSettle();
    expect(find.text('Processed'), findsOneWidget);
    expect(find.text('Conversation created'), findsNothing);
    expect(find.textContaining('Cloud copies are kept'), findsNothing);
    expect(tester.takeException(), isNull);
    await _capture(tester, '004-mobile-ios-sync-processed.png');
  });

  testWidgets('127 uploaded recordings remain processing, not complete or a queue-clearing instruction',
      (tester) async {
    await _pump(tester, const AutoSyncPage(), WalStatus.uploaded, recordings: [
      for (var i = 0; i < 127; i++)
        Wal(
            timerStart: 1790730000 + i * 10,
            codec: BleAudioCodec.opus,
            seconds: 10,
            status: WalStatus.uploaded,
            storage: WalStorage.disk,
            device: 'pendant')
          ..jobId = 'job-$i',
    ]);
    final l = AppLocalizations.of(tester.element(find.byType(AutoSyncPage)));
    expect(find.text(l.syncCardTranscribingAmount(OmiDuration.compact(1270, l))), findsOneWidget);
    expect(find.text('All recordings synced'), findsNothing);
    expect(find.text('All caught up'), findsNothing);
    expect(find.text('Conversation created'), findsNothing);
    expect(tester.takeException(), isNull);
    await _capture(tester, '005-mobile-ios-sync-pending-backlog.png');
  });
}
