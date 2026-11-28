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
import 'package:omi/pages/conversations/widgets/sync_details_sheet.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_derived_sync_views.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/sfpro_font_fixtures.dart';

class _Sync extends ChangeNotifier with WalDerivedSyncViews implements SyncProvider {
  _Sync(this.wals);
  final List<Wal> wals;
  @override
  SyncState syncState = const SyncState();
  @override
  bool get isRingDownloading => false;
  @override
  int get readyRingSeconds => freshRingBacklog?.seconds ?? 0;
  @override
  ({int seconds, int bytes})? freshRingBacklog;
  @override
  ({int processed, int total}) get offlineServerProcessingCounts => (processed: 0, total: 0);
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
  int get clearableWalsCount => wals.length;
  @override
  List<Wal> get syncedWals => wals.where((wal) => wal.status == WalStatus.synced).toList();
  @override
  List<Wal> get corruptedWals => wals
      .where((wal) => {
            WalStatus.corrupted,
            WalStatus.outsideRecoveryWindow,
            WalStatus.unsupportedAudio,
          }.contains(wal.status))
      .toList();
  @override
  List<Wal> get refusedWals => wals.where((wal) => wal.status == WalStatus.uploadRejected).toList();
  @override
  List<Wal> get pendingDeletableWals => missingWals;

  @override
  List<Wal> get retryableAttentionWals => derivedWals.retryable;
  @override
  bool get syncCompleted => false;
  @override
  WalStatusFilter get statusFilter => WalStatusFilter.pending;
  String? retainedPendingId;
  String? retainedSyncedId;
  bool failSyncedBulkAfterPartial = false;
  bool failClearAll = false;
  bool failDelete = false;
  List<Wal>? discoveredWals;

  @override
  Future<void> deleteAllPendingWals({String? firmwareVersion, bool refreshDevice = true}) async {
    try {
      final targets = pendingDeletableWals.map((wal) => wal.id).toSet();
      wals.removeWhere((wal) => targets.contains(wal.id) && wal.id != retainedPendingId);
      notifyListeners();
    } finally {
      if (refreshDevice) await discoverDeviceWals(firmwareVersion: firmwareVersion);
    }
  }

  @override
  Future<void> deleteAllSyncedWals({String? firmwareVersion, bool refreshDevice = true}) async {
    try {
      final targets = syncedWals.map((wal) => wal.id).toSet();
      wals.removeWhere((wal) => targets.contains(wal.id) && wal.id != retainedSyncedId);
      notifyListeners();
      if (failSyncedBulkAfterPartial) throw StateError('synthetic device ACK failure');
    } finally {
      if (refreshDevice) await discoverDeviceWals(firmwareVersion: firmwareVersion);
    }
  }

  @override
  Future<void> deleteAllClearableWals({String? firmwareVersion, bool refreshDevice = true}) async {
    try {
      if (failClearAll) throw StateError('synthetic device ACK failure');
    } finally {
      if (refreshDevice) await discoverDeviceWals(firmwareVersion: firmwareVersion);
    }
  }

  @override
  Future<void> deleteWal(Wal wal, {String? firmwareVersion, bool refreshDevice = true}) async {
    try {
      if (failDelete) throw StateError('synthetic device ACK failure');
      wals.removeWhere((item) => item.id == wal.id);
      notifyListeners();
    } finally {
      if (refreshDevice) await discoverDeviceWals(firmwareVersion: firmwareVersion);
    }
  }

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
  String currentFirmwareVersion = 'Unknown';
  @override
  bool isConnected = false;
  @override
  RingStatus? get ringStatus => null;
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

Future<_Sync> _pump(WidgetTester tester, Widget page, WalStatus status, {List<Wal>? recordings}) async {
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final sync = _SyncWithDiscovery(recordings ??
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

      for (final family in ['SF Pro Display']) {
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
    snackBarTheme: baseTheme.snackBarTheme.copyWith(
      contentTextStyle: baseTheme.snackBarTheme.contentTextStyle?.copyWith(fontFamily: 'SF Pro Display'),
    ),
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
  return sync;
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

Future<AppLocalizations> _clearPending(WidgetTester tester) async {
  final l = AppLocalizations.of(tester.element(find.byType(SyncPage)));
  await tester.tap(find.byTooltip(l.manageStorage));
  await tester.pumpAndSettle();
  await tester.tap(find.text(l.clear));
  await tester.pumpAndSettle();
  expect(find.text(l.deletePendingFiles), findsOneWidget);
  await tester.tap(find.text(l.clear));
  await tester.pumpAndSettle();
  return l;
}

Future<AppLocalizations> _clearSynced(WidgetTester tester) async {
  final l = AppLocalizations.of(tester.element(find.byType(SyncPage)));
  await tester.tap(find.byTooltip(l.manageStorage));
  await tester.pumpAndSettle();
  await tester.tap(find.text(l.clear).first);
  await tester.pumpAndSettle();
  expect(find.text(l.deleteSyncedFiles), findsOneWidget);
  await tester.tap(find.text(l.clear).last);
  await tester.pumpAndSettle();
  return l;
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

  for (final legacy in [false, true]) {
    testWidgets('expired upload cannot hide ready Sync action (legacy=$legacy)', (tester) async {
      final stale = Wal(
          timerStart: 1700000000,
          codec: BleAudioCodec.opus,
          seconds: 120,
          status: WalStatus.uploaded,
          storage: WalStorage.disk);
      final ready = Wal(
          timerStart: DateTime.now().millisecondsSinceEpoch ~/ 1000,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk);
      await _pump(tester, legacy ? const SyncPage() : const AutoSyncPage(), WalStatus.miss, recordings: [stale, ready]);
      final l = AppLocalizations.of(tester.element(find.byType(legacy ? SyncPage : AutoSyncPage)));
      expect(find.text(l.syncCardReadyAmount(OmiDuration.compact(60, l))), findsOneWidget);
      expect(find.text(l.sync), findsOneWidget);
      expect(stale.status, WalStatus.uploaded);
      expect(ready.status, WalStatus.miss);
      expect(tester.takeException(), isNull);
      await _capture(
          tester,
          legacy
              ? '006-mobile-ios-legacy-ready-with-stalled-upload.png'
              : '005-mobile-ios-sync-ready-with-stalled-upload.png');
    });

    testWidgets('expired uploads wait on the server calmly, without a processing spinner (legacy=$legacy)',
        (tester) async {
      final wal = Wal(
          timerStart: DateTime.now().subtract(const Duration(days: 40)).millisecondsSinceEpoch ~/ 1000,
          codec: BleAudioCodec.opus,
          seconds: 120,
          status: WalStatus.uploaded,
          storage: WalStorage.disk);
      await _pump(tester, legacy ? const SyncPage() : const AutoSyncPage(), WalStatus.uploaded, recordings: [wal]);
      // Card header and per-row label share one predicate (stalledUploadsAt), so they share one meaning.
      expect(find.text('Uploads waiting on the server'), findsOneWidget);
      expect(find.text('Uploaded, awaiting server'), findsWidgets);
      expect(find.text('Transcription unavailable'), findsNothing);
      expect(find.byType(OmiSpinner), findsNothing);
      expect(find.textContaining('Turning'), findsNothing);
      expect(wal.status, WalStatus.uploaded);
      expect(walDeletionAllowed(wal), isFalse);
    });
  }

  testWidgets('an expired upload cannot hide another recording Retry action', (tester) async {
    final stale = Wal(
        timerStart: 1700000000,
        codec: BleAudioCodec.opus,
        seconds: 120,
        status: WalStatus.uploaded,
        storage: WalStorage.disk);
    final failed = Wal(
        timerStart: 1700001000,
        codec: BleAudioCodec.opus,
        seconds: 30,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        retryCount: walMaxAutoRetries);
    await _pump(tester, const AutoSyncPage(), WalStatus.uploaded, recordings: [stale, failed]);
    expect(find.byKey(const Key('offline_sync_card_retry_attention')), findsOneWidget);
  });

  testWidgets('Auto Sync keeps idle work in preparation until a transfer phase starts', (tester) async {
    final sync = await _pump(tester, const AutoSyncPage(), WalStatus.miss);
    sync.syncState = const SyncState(status: SyncStatus.syncing, phase: SyncPhase.idle);
    sync.notifyListeners();
    await tester.pump();

    final l = AppLocalizations.of(tester.element(find.byType(AutoSyncPage)));
    expect(find.text(l.syncCardSyncingTitle), findsOneWidget);
    expect(find.text(l.syncCardProcessing), findsNothing);
    expect(find.text(l.syncDetailsTranscribing), findsNothing);
    await tester.pump(const Duration(milliseconds: 300));
    await _capture(tester, '001-mobile-ios-sync-preparation.png');
  });

  testWidgets('Sync details shows fresh ring audio without a virtual WAL and otherwise shows unknown', (tester) async {
    final sync = await _pump(tester, const AutoSyncPage(), WalStatus.miss, recordings: []);
    final element = tester.element(find.byType(AutoSyncPage));
    final device = element.read<DeviceProvider>() as _Device;
    device.currentFirmwareVersion = '3.0.25';
    device.isConnected = true;
    final l = AppLocalizations.of(element);

    sync.freshRingBacklog = (seconds: 90, bytes: 800000);
    sync.notifyListeners();
    await tester.pump();
    expect(find.text(l.syncCardReadyAmount(OmiDuration.compact(90, l))), findsOneWidget);
    await tester.tap(find.text(l.syncDetailsTitle));
    await tester.pumpAndSettle();
    expect(find.byType(SyncDetailsSheet), findsOneWidget);
    expect(
      find.descendant(
        of: find.byType(SyncDetailsSheet),
        matching: find.textContaining(OmiDuration.compact(90, l)),
      ),
      findsOneWidget,
    );
    expect(find.text(l.unknown), findsNothing);
    await _capture(tester, '002-mobile-ios-fresh-ring-backlog.png');

    sync.freshRingBacklog = null;
    sync.notifyListeners();
    await tester.pump();
    expect(find.text(l.unknown), findsOneWidget);
    await _capture(tester, '003-mobile-ios-unknown-ring-backlog.png');
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
            uploadedAt: DateTime.now().millisecondsSinceEpoch ~/ 1000,
            storage: WalStorage.disk,
            device: 'pendant')
          ..jobId = 'job-$i',
    ]);
    final l = AppLocalizations.of(tester.element(find.byType(AutoSyncPage)));
    expect(find.text('${l.syncDetailsTranscribing} · ${OmiDuration.compact(1270, l)}'), findsOneWidget);
    expect(find.text('All recordings synced'), findsNothing);
    expect(find.text('All caught up'), findsNothing);
    expect(find.text('Conversation created'), findsNothing);
    expect(tester.takeException(), isNull);
    await _capture(tester, '005-mobile-ios-sync-pending-backlog.png');
  });

  for (final retainOne in [true, false]) {
    testWidgets('Classic Clear Pending reports the actual result (retained: $retainOne)', (tester) async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final pending = [
        for (final secondsAgo in [30, 60])
          Wal(
              timerStart: now - secondsAgo,
              codec: BleAudioCodec.opus,
              seconds: 30,
              storage: WalStorage.disk,
              status: WalStatus.miss),
      ];
      final retained = pending.first;
      final sync = await _pump(tester, const SyncPage(), WalStatus.miss, recordings: pending);
      if (retainOne) sync.retainedPendingId = retained.id;
      final l = await _clearPending(tester);

      expect(sync.allWals, retainOne ? [retained] : isEmpty);
      expect(find.text(l.failedToDeleteSomeItems), retainOne ? findsOneWidget : findsNothing);
      expect(find.text(l.pendingFilesDeleted), retainOne ? findsNothing : findsOneWidget);
      await _capture(tester, retainOne ? '001-mobile-ios-pending-retained.png' : '002-mobile-ios-pending-cleared.png');
    });
  }

  testWidgets('Classic Clear Synced reports a partial failure and keeps the retained recording', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final retained = Wal(
      timerStart: now - 60,
      codec: BleAudioCodec.opus,
      seconds: 30,
      storage: WalStorage.disk,
      status: WalStatus.synced,
      device: 'phone',
    );
    final deleted = Wal(
      timerStart: now - 30,
      codec: BleAudioCodec.opus,
      seconds: 30,
      storage: WalStorage.disk,
      status: WalStatus.synced,
      device: 'phone',
    );
    final sync = await _pump(tester, const SyncPage(), WalStatus.synced, recordings: [retained, deleted]);
    sync
      ..retainedSyncedId = retained.id
      ..failSyncedBulkAfterPartial = true;

    final l = await _clearSynced(tester);

    expect(sync.allWals, [retained]);
    expect(find.text(l.failedToDeleteSomeItems), findsOneWidget);
    expect(find.text(l.syncedFilesDeleted), findsNothing);
  });

  testWidgets('Classic Clear Synced ignores newly discovered pending ring audio', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    Wal ring(int start, WalStatus status) => Wal(
          timerStart: start,
          codec: BleAudioCodec.opus,
          seconds: 30,
          storage: WalStorage.sdcard,
          status: status,
          device: 'synthetic-pendant',
          fileNum: -1,
        );

    final original = ring(now - 30, WalStatus.synced);
    final newlyDiscovered = ring(now - 29, WalStatus.miss);
    final sync = await _pump(tester, const SyncPage(), WalStatus.synced, recordings: [original]);
    sync.discoveredWals = [newlyDiscovered];

    final l = await _clearSynced(tester);

    expect(sync.allWals, [newlyDiscovered]);
    expect(find.text(l.failedToDeleteSomeItems), findsNothing);
    expect(find.text(l.syncedFilesDeleted), findsOneWidget);
  });

  testWidgets('Classic Clear Synced reports a retained non-ring device row after rediscovery', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    Wal sdcard(int start, WalStatus status) => Wal(
          timerStart: start,
          codec: BleAudioCodec.opus,
          seconds: 30,
          storage: WalStorage.sdcard,
          status: status,
          device: 'synthetic-pendant',
          fileNum: 4,
        );

    final original = sdcard(now - 30, WalStatus.synced);
    final retainedPending = sdcard(now - 30, WalStatus.miss);
    final sync = await _pump(tester, const SyncPage(), WalStatus.synced, recordings: [original]);
    sync
      ..retainedSyncedId = original.id
      ..discoveredWals = [retainedPending];

    final l = await _clearSynced(tester);

    expect(sync.allWals, [retainedPending]);
    expect(find.text(l.failedToDeleteSomeItems), findsOneWidget);
    expect(find.text(l.syncedFilesDeleted), findsNothing);
  });

  testWidgets('Sync row swipe keeps a WAL visible when device deletion is refused', (tester) async {
    final row = Wal(
      timerStart: 1790730000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.miss,
      storage: WalStorage.flashPage,
      device: 'synthetic-pendant',
      storageTotalBytes: 100,
    );
    final sync = await _pump(tester, const SyncPage(), WalStatus.miss, recordings: [row]);
    sync.failDelete = true;

    final l = AppLocalizations.of(tester.element(find.byType(SyncPage)));
    await tester.drag(find.byKey(Key(row.id)), const Offset(-500, 0));
    await tester.pumpAndSettle();
    expect(find.text(l.deleteRecording), findsOneWidget);
    await tester.tap(find.text(l.delete));
    await tester.pumpAndSettle();

    expect(find.byKey(Key(row.id)), findsOneWidget);
    expect(find.text(l.failedToDeleteSomeItems), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Classic Clear All reports an ACK failure', (tester) async {
    final sync = await _pump(tester, const SyncPage(), WalStatus.synced);
    sync.failClearAll = true;
    final l = AppLocalizations.of(tester.element(find.byType(SyncPage)));

    await tester.tap(find.byTooltip(l.manageStorage));
    await tester.pumpAndSettle();
    await tester.tap(find.text(l.clearAll));
    await tester.pumpAndSettle();
    expect(find.text(l.deleteAllFiles), findsOneWidget);
    await tester.tap(find.text(l.clearAll));
    await tester.pumpAndSettle();

    expect(find.text(l.failedToDeleteSomeItems), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Classic Clear All reports a WAL retained after a normal return', (tester) async {
    final sync = await _pump(tester, const SyncPage(), WalStatus.synced);
    final retained = sync.allWals.single;
    final l = AppLocalizations.of(tester.element(find.byType(SyncPage)));

    await tester.tap(find.byTooltip(l.manageStorage));
    await tester.pumpAndSettle();
    await tester.tap(find.text(l.clearAll));
    await tester.pumpAndSettle();
    expect(find.text(l.deleteAllFiles), findsOneWidget);
    await tester.tap(find.text(l.clearAll));
    await tester.pumpAndSettle();

    expect(sync.allWals, [retained]);
    expect(find.text(l.failedToDeleteSomeItems), findsOneWidget);
    expect(find.text(l.allFilesDeleted), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Classic Clear Pending reports a retained ring after its virtual row is rebuilt', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    Wal ring(int start) => Wal(
          timerStart: start,
          codec: BleAudioCodec.opus,
          seconds: 30,
          storage: WalStorage.sdcard,
          status: WalStatus.miss,
          device: 'synthetic-pendant',
          fileNum: -1,
        );

    final original = ring(now - 30);
    final rediscovered = ring(now - 29);
    final sync = await _pump(tester, const SyncPage(), WalStatus.miss, recordings: [original]);
    sync.retainedPendingId = original.id;
    sync.discoveredWals = [rediscovered];
    expect(rediscovered.id, isNot(original.id));

    final l = await _clearPending(tester);

    expect(sync.allWals, [rediscovered]);
    expect(find.text(l.failedToDeleteSomeItems), findsOneWidget);
    expect(find.text(l.pendingFilesDeleted), findsNothing);
  });

  testWidgets('row delete reports a rebuilt ring that remains in the inventory', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    Wal ring(int start) => Wal(
          timerStart: start,
          codec: BleAudioCodec.opus,
          seconds: 30,
          storage: WalStorage.sdcard,
          status: WalStatus.miss,
          device: 'synthetic-pendant',
          fileNum: -1,
        );

    final original = ring(now - 30);
    final rediscovered = ring(now - 29);
    final sync = await _pump(tester, const SyncPage(), WalStatus.miss, recordings: [original]);
    sync.discoveredWals = [rediscovered];
    final l = AppLocalizations.of(tester.element(find.byType(SyncPage)));

    await tester.drag(find.byKey(Key(original.id)), const Offset(-500, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.text(l.delete));
    await tester.pumpAndSettle();

    expect(find.byKey(Key(rediscovered.id)), findsOneWidget);
    expect(find.text(l.failedToDeleteSomeItems), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('empty Clear All confirms that there are no recordings', (tester) async {
    final wal = Wal(
      timerStart: DateTime.now().millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.miss,
      storage: WalStorage.disk,
    );
    final sync = await _pump(tester, const SyncPage(), WalStatus.miss, recordings: [wal]);
    final l = AppLocalizations.of(tester.element(find.byType(SyncPage)));

    await tester.tap(find.byTooltip(l.manageStorage));
    await tester.pumpAndSettle();
    // The sheet was opened with a nonempty snapshot; another refresh can empty
    // the provider before the user taps its still-visible action.
    sync.wals.clear();
    sync.notifyListeners();
    await tester.pumpAndSettle();
    await tester.tap(find.text(l.clearAll));
    await tester.pumpAndSettle();
    expect(find.text(l.deleteAllFiles), findsOneWidget);
    await tester.tap(find.text(l.clearAll));
    await tester.pumpAndSettle();

    expect(sync.allWals, isEmpty);
    expect(find.text(l.noRecordings).last, findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

class _SyncWithDiscovery extends _Sync {
  _SyncWithDiscovery(super.wals);

  @override
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {
    final refreshed = discoveredWals;
    if (refreshed == null) return;
    wals
      ..clear()
      ..addAll(refreshed);
    notifyListeners();
  }
}
