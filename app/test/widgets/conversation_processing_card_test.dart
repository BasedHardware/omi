import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart' show BleAudioCodec;
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/widgets/capture_recovery_banner.dart';
import 'package:omi/pages/conversations/widgets/conversation_processing_card.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';

/// Home's Offline Sync status card: recordings still becoming conversations
/// stay visible, with a tap-through to the Offline Sync page. Home used to go
/// quiet the moment a conversation ended, and the newest row kept its old
/// timestamp — which read as stuck.

class _FakeSync extends ChangeNotifier implements SyncProvider {
  _FakeSync(
      {this.wals = const [],
      this.syncing = false,
      this.fetching = false,
      this.fetchingWithUploadPhase = false,
      this.progress = 0.0});

  final List<Wal> wals;
  final bool syncing;
  final bool fetching;

  /// Models the real upload→fetch transition, which retains the uploading
  /// phase instead of moving to idle.
  final bool fetchingWithUploadPhase;
  final double progress;
  bool rateLimited = false;
  RateLimitReason? reason;

  @override
  SyncState get syncState => switch ((syncing, fetching, fetchingWithUploadPhase)) {
        (true, _, _) =>
          SyncState(status: SyncStatus.syncing, phase: SyncPhase.downloadingFromDevice, progress: progress),
        (_, true, _) => const SyncState(status: SyncStatus.fetchingConversations),
        (_, _, true) => const SyncState(status: SyncStatus.fetchingConversations, phase: SyncPhase.uploadingToCloud),
        _ => const SyncState(),
      };
  @override
  bool get isSyncing => syncing;
  @override
  List<Wal> get allWals => wals;

  /// The real provider returns a memoized newest-first sort; mirror that
  /// contract, because grouping correctness depends on the order.
  @override
  List<Wal> get displaySortedWals {
    final list = List<Wal>.from(wals);
    list.sort((a, b) => b.timerStart.compareTo(a.timerStart));
    return list;
  }

  @override
  List<Wal> get missingWals => wals.where((w) => w.status == WalStatus.miss).toList();
  @override
  List<Wal> get filteredByStatusWals => missingWals;
  @override
  WalStatusFilter get statusFilter => WalStatusFilter.pending;
  @override
  int get pendingStatusCount => missingWals.length;
  @override
  int get syncedStatusCount => wals.where((w) => w.status == WalStatus.synced).length;
  @override
  int get corruptedStatusCount => wals.where((w) => w.status == WalStatus.corrupted).length;
  @override
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) => wals;
  @override
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {}
  @override
  Future<void> refreshWals() async {}
  @override
  bool get isLoadingWals => false;
  @override
  int get clearableWalsCount => 0;
  @override
  int get missingWalsInSeconds => wals.isEmpty ? 0 : wals.map((w) => w.seconds).reduce((a, b) => a + b);
  @override
  List<Wal> get uploadedWals => wals.where((w) => w.status == WalStatus.uploaded).toList();
  @override
  bool get isRateLimited => rateLimited;
  @override
  RateLimitReason? get rateLimitReason => reason;
  @override
  String? get syncError => null;
  @override
  Wal? get failedWal => null;
  @override
  double? get syncSpeedKBps => null;
  // AutoSyncPage's status card reads this when the tap lands there; false keeps
  // its "N conversations created" link out of the pushed page.
  @override
  bool get syncCompleted => false;
  @override
  ({int processed, int total}) get offlineServerProcessingCounts {
    final total = uploadedWals.length;
    final done = uploadedWals.where((w) => w.status == WalStatus.synced).length;
    return (processed: done, total: total);
  }

  @override
  ({int doneSeconds, int totalSeconds, bool tracked}) get offlineServerProcessingSeconds {
    // Models a tracked upload batch: everything uploaded stays in the total
    // until its job resolves (status moves to synced).
    final batch = wals.where((w) => w.status == WalStatus.uploaded || w.status == WalStatus.synced).toList();
    if (batch.isEmpty) return (doneSeconds: 0, totalSeconds: 0, tracked: false);
    final total = batch.fold(0, (sum, w) => sum + w.seconds);
    final done = batch.fold(0, (sum, w) => sum + (w.status == WalStatus.synced ? w.seconds : 0));
    return (doneSeconds: done, totalSeconds: total, tracked: true);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Wal _wal(String id, int minutes, WalStatus status) => Wal(
      timerStart: 1000 + id.length,
      codec: BleAudioCodec.opus,
      seconds: minutes * 60,
      status: status,
      storage: WalStorage.disk,
      device: 'pendant',
    );

Future<void> _pump(WidgetTester tester, SyncProvider sync,
    {List<SingleChildWidget> extras = const [], bool multiFile = false}) async {
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ...extras,
        ChangeNotifierProvider<SyncProvider>.value(value: sync),
      ],
      child: MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SingleChildScrollView(
            child: ConversationProcessingCard(multiFileSync: multiFile),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

/// AutoSyncPage reads the paired device's capabilities; the card's route
/// pushes it. `storageSupport` mirrors the v2 gate the device settings apply
/// before they open Offline Sync.
class _Device extends ChangeNotifier implements DeviceProvider {
  _Device({this.storageSupport = true});

  final bool storageSupport;

  @override
  bool get isDeviceStorageSupport => storageSupport;
  @override
  String get currentFirmwareVersion => 'Unknown';
  @override
  Future<void> refreshRingStorageStatus() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('ConversationProcessingCard', () {
    testWidgets('shows a finished recording while the server still processes it', (tester) async {
      final sync = _FakeSync(
        wals: [_wal('processing', 40, WalStatus.uploaded), _wal('done', 15, WalStatus.synced)],
      );

      await _pump(tester, sync, multiFile: true);

      expect(find.byKey(const Key('conversation_processing_card')), findsOneWidget);
      expect(find.text('Turning 55m into conversations'), findsOneWidget);
      expect(find.text('15m of 55m done · you can leave this screen'), findsOneWidget);
    });

    testWidgets('hides once every recording is a conversation', (tester) async {
      final sync = _FakeSync(wals: [_wal('done', 15, WalStatus.synced)]);

      await _pump(tester, sync);

      expect(find.byKey(const Key('conversation_processing_card')), findsNothing);
    });

    testWidgets('shows a live sync with the device step and an amount', (tester) async {
      final wal = _wal('moving', 10, WalStatus.miss)
        ..storage = WalStorage.sdcard
        ..storageTotalBytes = 10 * 60 * 32000
        ..storageOffset = 5 * 60 * 32000;
      final sync = _FakeSync(wals: [wal], syncing: true, progress: 0.5);

      await _pump(tester, sync, multiFile: true);

      expect(find.text('Syncing 10m of audio'), findsOneWidget);
      expect(find.text('Downloading from your Omi · 5m of 10m'), findsOneWidget);
    });

    testWidgets('offers the tap when recordings wait for a sync', (tester) async {
      SharedPreferencesUtil().autoSyncOfflineRecordings = false;
      final sync = _FakeSync(wals: [_wal('ready-a', 45, WalStatus.miss), _wal('ready-b', 15, WalStatus.miss)]);

      await _pump(tester, sync, multiFile: true);

      expect(find.byKey(const Key('conversation_processing_card')), findsOneWidget);
      expect(find.text('1h ready to sync'), findsOneWidget);
    });

    testWidgets('shows recordings ready for the automatic sync, not a stale timestamp', (tester) async {
      final sync = _FakeSync(wals: [_wal('ready', 45, WalStatus.miss)]);

      await _pump(tester, sync);

      expect(find.byKey(const Key('conversation_processing_card')), findsOneWidget);
      expect(find.text('45m ready to sync'), findsOneWidget);
    });

    testWidgets('keeps the processing copy through the post-sync conversation fetch', (tester) async {
      final sync = _FakeSync(fetching: true);

      await _pump(tester, sync, multiFile: true);

      // The fetch window is the settings page's active window too; Home must
      // not fall back to ready copy while conversations are still loading.
      expect(find.byKey(const Key('conversation_processing_card')), findsOneWidget);
      expect(find.text('Processing on Omi…'), findsOneWidget);
    });

    testWidgets('shows server processing when the fetch keeps the uploading phase', (tester) async {
      // The real transition to the fetch retains the uploading phase, so
      // phase alone cannot tell "still uploading" from "already fetching".
      final sync = _FakeSync(
        wals: [_wal('processing', 40, WalStatus.uploaded)],
        fetchingWithUploadPhase: true,
      );

      await _pump(tester, sync, multiFile: true);

      expect(find.byKey(const Key('conversation_processing_card')), findsOneWidget);
      expect(find.text('Turning 40m into conversations'), findsOneWidget);
      expect(find.text('Syncing 40m of audio'), findsNothing);
    });

    testWidgets('reads a backend-busy cooldown as itself, not pending work', (tester) async {
      final sync = _FakeSync(wals: [_wal('waiting', 45, WalStatus.miss)])
        ..rateLimited = true
        ..reason = RateLimitReason.backendBusy;

      await _pump(tester, sync, multiFile: true);

      expect(find.byKey(const Key('conversation_processing_card')), findsOneWidget);
      expect(find.text('Omi servers are busy — your recordings will sync once capacity returns'), findsOneWidget);
    });

    testWidgets('hides when only retry-exhausted recordings remain', (tester) async {
      // A backlog the automatic sync has given up on is the Offline Sync
      // page's to surface; a permanent card on Home would just be noise.
      final exhausted = _wal('exhausted', 20, WalStatus.miss)..retryCount = walMaxAutoRetries;
      expect(exhausted.syncDisplayState, WalSyncDisplayState.failed);
      final sync = _FakeSync(wals: [exhausted]);

      await _pump(tester, sync, multiFile: true);

      expect(find.byKey(const Key('conversation_processing_card')), findsNothing);
    });

    testWidgets('hides when only local-only (on-device STT) recordings remain', (tester) async {
      // On-device STT never uploads these, so a card claiming they are ready
      // to sync could never clear. They stay visible where they belong: the
      // conversations themselves.
      final localOnly = _wal('local-only', 30, WalStatus.miss)..onDeviceOnly = true;
      final sync = _FakeSync(wals: [localOnly]);

      await _pump(tester, sync, multiFile: true);

      expect(find.byKey(const Key('conversation_processing_card')), findsNothing);
    });

    testWidgets('counts only syncable recordings in the ready amount', (tester) async {
      SharedPreferencesUtil().autoSyncOfflineRecordings = false;
      final sync = _FakeSync(wals: [
        _wal('ready', 45, WalStatus.miss),
        _wal('local-only', 30, WalStatus.miss)..onDeviceOnly = true,
      ]);

      await _pump(tester, sync, multiFile: true);

      // 45m, not 1h 15m: the local-only recording is not waiting on a sync.
      expect(find.text('45m ready to sync'), findsOneWidget);
    });

    testWidgets('counts fragments of one recording as one, whatever order they arrive', (tester) async {
      SharedPreferencesUtil().autoSyncOfflineRecordings = false;
      // allWals preserves storage-source order (here oldest-first); grouping
      // must not read contiguous fragments as separate recordings. Fragments
      // without a known length take the count title, which shows the grouping.
      final sync = _FakeSync(wals: [
        _wal('frag-a', 0, WalStatus.miss)..timerStart = 1000,
        _wal('frag-b', 0, WalStatus.miss)..timerStart = 1060,
        _wal('frag-c', 0, WalStatus.miss)..timerStart = 1120,
      ]);

      await _pump(tester, sync, multiFile: true);

      expect(find.byKey(const Key('conversation_processing_card')), findsOneWidget);
      // Three contiguous fragments are one recording, not three.
      expect(find.text('1 recording ready to sync'), findsOneWidget);
    });

    testWidgets('tapping opens the Offline Sync page the device settings open', (tester) async {
      final sync = _FakeSync(wals: [_wal('processing', 40, WalStatus.uploaded)]);

      await _pump(tester, sync, multiFile: true, extras: [
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device()),
      ]);

      await tester.tap(find.byKey(const Key('conversation_processing_card')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      // The multi-file page's status-card link; the single-file page has none.
      expect(find.text('Sync details'), findsOneWidget);
    });

    testWidgets('tapping routes to the single-file page when multi-file sync is off', (tester) async {
      final sync = _FakeSync(wals: [_wal('processing', 40, WalStatus.uploaded)]);

      await _pump(tester, sync, multiFile: false, extras: [
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device()),
      ]);

      await tester.tap(find.byKey(const Key('conversation_processing_card')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      // The single-file page's app-bar Manage Storage action; the multi-file
      // page has no app bar actions.
      expect(find.byTooltip('Manage Storage'), findsOneWidget);
    });

    testWidgets('tapping shows the v2 alert when device-resident work has no storage support', (tester) async {
      final pending = _wal('pending', 40, WalStatus.miss)..storage = WalStorage.sdcard;
      final sync = _FakeSync(wals: [pending]);

      await _pump(tester, sync, multiFile: true, extras: [
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device(storageSupport: false)),
      ]);

      await tester.tap(find.byKey(const Key('conversation_processing_card')));
      await tester.pump();

      // The device settings' alert, not a pushed Offline Sync page.
      expect(find.text('Offline Sync unavailable'), findsOneWidget);
      expect(find.text('Offline Sync'), findsNothing);
    });

    testWidgets('tapping opens the sync page with no device when only phone/server work remains', (tester) async {
      // The pendant can be disconnected — even storage-less: phone WALs and
      // server jobs need no connected device, so the card must not strand that
      // work behind the "Offline Sync unavailable" alert.
      final sync = _FakeSync(wals: [_wal('processing', 40, WalStatus.uploaded)]);

      await _pump(tester, sync, multiFile: true, extras: [
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device(storageSupport: false)),
      ]);

      await tester.tap(find.byKey(const Key('conversation_processing_card')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      // The multi-file page's status-card link; the single-file page has none.
      expect(find.text('Sync details'), findsOneWidget);
    });

    testWidgets('a lagging device twin does not block the tap once its phone copy moved', (tester) async {
      // Importing device audio leaves the device twin `miss` (same
      // device_timerStart id) while the phone copy uploads; the twin is
      // bookkeeping lag, not pending device work, so the tap must open.
      final phone = _wal('twin', 40, WalStatus.uploaded);
      final deviceTwin = _wal('twin', 40, WalStatus.miss)..storage = WalStorage.sdcard;
      final sync = _FakeSync(wals: [phone, deviceTwin]);

      await _pump(tester, sync, multiFile: true, extras: [
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device(storageSupport: false)),
      ]);

      await tester.tap(find.byKey(const Key('conversation_processing_card')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(find.text('Offline Sync unavailable'), findsNothing);
      expect(find.text('Sync details'), findsOneWidget);
    });

    testWidgets('names what needs the user before anything else', (tester) async {
      SharedPreferencesUtil().autoSyncOfflineRecordings = false;
      final sync = _FakeSync(
        wals: [_wal('too-old', 3, WalStatus.outsideRecoveryWindow), _wal('ready', 45, WalStatus.miss)],
      );

      await _pump(tester, sync, multiFile: true);

      // count=1 takes the =1 branch, so the rendered copy is literally
      // "1 recording need attention" (the plural suffix lives in `other`).
      expect(find.text('1 recording need attention'), findsOneWidget);
    });

    // Home mounts the card inside a CustomScrollView's slivers, where a plain
    // box widget (SizedBox.shrink included) asserts against the viewport. This
    // mirrors that mount so the box/sliver contract cannot regress unseen.
    testWidgets('mounts inside Home sliver list, hidden and visible', (tester) async {
      Widget host(SyncProvider sync) => MultiProvider(
            providers: [ChangeNotifierProvider<SyncProvider>.value(value: sync)],
            child: const MaterialApp(
              localizationsDelegates: [
                AppLocalizations.delegate,
                GlobalMaterialLocalizations.delegate,
                GlobalWidgetsLocalizations.delegate,
                GlobalCupertinoLocalizations.delegate,
              ],
              supportedLocales: AppLocalizations.supportedLocales,
              home: Scaffold(
                body: CustomScrollView(
                  slivers: [
                    SliverToBoxAdapter(child: CaptureRecoveryBanner()),
                    SliverToBoxAdapter(child: ConversationProcessingCard()),
                  ],
                ),
              ),
            ),
          );

      await tester.pumpWidget(host(_FakeSync(wals: [_wal('done', 15, WalStatus.synced)])));
      await tester.pump();
      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('conversation_processing_card')), findsNothing);

      await tester.pumpWidget(host(_FakeSync(wals: [_wal('processing', 40, WalStatus.uploaded)])));
      await tester.pump();
      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('conversation_processing_card')), findsOneWidget);
    });
  });
}
