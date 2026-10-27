import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart' show BleAudioCodec;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart' show NoConversationsHero;
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';

import '../support/typed_conversation_screen.dart';

/// Home's pending row and the On the Way page: recordings still becoming
/// conversations stay visible in Today as one calm row, with the detail one
/// tap away and the Offline Sync page one tap beyond that.

class _FakeSync extends ChangeNotifier implements SyncProvider {
  _FakeSync({this.wals = const [], this.syncing = false, this.fetching = false, this.fetchingWithUploadPhase = false});

  final List<Wal> wals;
  final bool syncing;
  final bool fetching;

  /// Models the real upload→fetch transition, which retains the uploading
  /// phase instead of moving to idle.
  final bool fetchingWithUploadPhase;
  bool rateLimited = false;
  RateLimitReason? reason;

  @override
  SyncState get syncState => switch ((syncing, fetching, fetchingWithUploadPhase)) {
        (true, _, _) => const SyncState(status: SyncStatus.syncing, phase: SyncPhase.downloadingFromDevice),
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

/// Fixtures sit at a fixed plausible instant (a 2026 morning): the page treats
/// pre-2024 clock values as a never-set device clock and lists them undated, so
/// placeholder epochs like 1000 no longer land on Today.
final int _baseSeconds = DateTime(2026, 9, 17, 9).millisecondsSinceEpoch ~/ 1000;

Wal _wal(String id, int minutes, WalStatus status) => Wal(
      timerStart: _baseSeconds + id.length,
      codec: BleAudioCodec.opus,
      seconds: minutes * 60,
      status: status,
      storage: WalStorage.disk,
      device: 'pendant',
    );

Widget _app(SyncProvider sync, Widget child, {List<SingleChildWidget> extras = const []}) => MultiProvider(
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
        home: child,
      ),
    );

Future<void> _pumpPage(WidgetTester tester, SyncProvider sync, {List<SingleChildWidget> extras = const []}) async {
  // The fixtures sit at the pinned 2026 instant: Today there so their day opens by default.
  OnTheWayPage.resetFolds();
  await tester.pumpWidget(
    _app(sync,
        OnTheWayPage(multiFileSync: true, clock: () => DateTime.fromMillisecondsSinceEpoch((_baseSeconds + 60) * 1000)),
        extras: extras),
  );
  await tester.pump();
}

const _row = Key('home_pending_row');

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

  group('OnTheWayPage', () {
    Future<PendingWorkStore> serverWork(List<PendingWorkItem> items) async {
      final store = PendingWorkStore(
        loadPending: () async => ApiSuccess(PendingWorkSnapshot(enabled: true, attentionUnseenCount: 0, items: items)),
        loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
      );
      await store.refresh();
      return store;
    }

    Future<void> pumpWithServerWork(WidgetTester tester, SyncProvider sync, PendingWorkStore store) async {
      OnTheWayPage.resetFolds();
      await tester.pumpWidget(_app(
        sync,
        OnTheWayPage(
          multiFileSync: true,
          pendingWork: store,
          clock: () => DateTime.fromMillisecondsSinceEpoch((_baseSeconds + 60) * 1000),
        ),
      ));
      await tester.pump();
    }

    testWidgets('lists server work the phone did not start instead of saying all is synced', (tester) async {
      final store = await serverWork([
        PendingWorkItem(
          id: 'conv:a',
          kind: 'conversation',
          state: 'summarizing',
          conversationIds: const ['a'],
          startedAt: DateTime.fromMillisecondsSinceEpoch((_baseSeconds - 100) * 1000),
          durationSeconds: 600,
        ),
        const PendingWorkItem(id: 'sync:j', kind: 'sync_job', state: 'transcribing', conversationIds: []),
      ]);
      await pumpWithServerWork(tester, _FakeSync(), store);

      expect(find.text('All recordings are synced'), findsNothing);
      expect(find.text('Processing'), findsOneWidget, reason: 'the summarizing conversation, on its day');
      expect(find.text('Transcribing…'), findsOneWidget, reason: 'the undated sync job');
    });

    testWidgets('a server sync job the phone is uploading itself is not listed twice', (tester) async {
      final store = await serverWork([
        const PendingWorkItem(id: 'sync:j', kind: 'sync_job', state: 'transcribing', conversationIds: []),
      ]);
      await pumpWithServerWork(tester, _FakeSync(wals: [_wal('phone', 4, WalStatus.uploaded)]), store);

      expect(find.text('Transcribing…'), findsOneWidget, reason: 'the recording only, not the job again');
    });

    testWidgets('a refused recording does not hide a server sync job', (tester) async {
      final store = await serverWork([
        const PendingWorkItem(id: 'sync:j', kind: 'sync_job', state: 'transcribing', conversationIds: []),
      ]);
      await pumpWithServerWork(tester, _FakeSync(wals: [_wal('too-old', 3, WalStatus.outsideRecoveryWindow)]), store);

      expect(find.text('1 recording need attention'), findsOneWidget);
      expect(find.text('Transcribing…'), findsOneWidget, reason: 'nothing on the phone is uploading the job');
    });

    testWidgets('shows how close each recording is to done', (tester) async {
      final device = _wal('device', 2, WalStatus.miss)..storage = WalStorage.sdcard;
      await _pumpPage(tester, _FakeSync(wals: [_wal('processing', 4, WalStatus.uploaded), device]));

      expect(find.text('Transcribing…'), findsOneWidget);
      expect(find.text('On your device'), findsOneWidget);
    });

    testWidgets('a lagging device twin is not listed once its phone copy moved', (tester) async {
      final phone = _wal('twin', 4, WalStatus.uploaded);
      final deviceTwin = _wal('twin', 4, WalStatus.miss)..storage = WalStorage.sdcard;
      await _pumpPage(tester, _FakeSync(wals: [phone, deviceTwin]));

      expect(find.text('On your device'), findsNothing);
      expect(find.text('Transcribing…'), findsOneWidget);
    });

    testWidgets('a fully synced twin hides its lagging device source completely', (tester) async {
      final phone = _wal('twin', 4, WalStatus.synced);
      final deviceTwin = _wal('twin', 4, WalStatus.miss)..storage = WalStorage.sdcard;
      await _pumpPage(tester, _FakeSync(wals: [phone, deviceTwin]));

      expect(find.text('All recordings are synced'), findsOneWidget);
    });

    testWidgets('counts fragments of one recording as one row', (tester) async {
      final a = Wal(
        timerStart: _baseSeconds,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.miss,
        device: 'pendant',
      );
      final b = Wal(
        timerStart: _baseSeconds + 60,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.miss,
        device: 'pendant',
      );
      await _pumpPage(tester, _FakeSync(wals: [b, a]));
      expect(find.text('Waiting to sync'), findsOneWidget);
    });

    test('a device drain in progress lists the recording once, not its copied pieces too', () {
      final source = Wal(
        timerStart: _baseSeconds,
        codec: BleAudioCodec.opus,
        seconds: 600,
        status: WalStatus.miss,
        storage: WalStorage.sdcard,
        device: 'pendant',
      );
      Wal piece(int start) => Wal(
            timerStart: start,
            codec: BleAudioCodec.opus,
            seconds: 60,
            status: WalStatus.miss,
            storage: WalStorage.disk,
            originalStorage: WalStorage.sdcard,
            device: 'pendant',
          );
      final phoneOnly = Wal(
        timerStart: _baseSeconds + 4000,
        codec: BleAudioCodec.opus,
        seconds: 60,
        status: WalStatus.miss,
        device: 'pendant',
      );
      final ids = SyncPendingWork.syncing(
        _FakeSync(wals: [source, piece(_baseSeconds), piece(_baseSeconds + 60), phoneOnly]),
      ).map((w) => w.timerStart).toList();
      expect(ids, [_baseSeconds + 4000, _baseSeconds]);
      expect(SyncPendingWork.syncing(_FakeSync(wals: [source, piece(_baseSeconds)])).single.storage, WalStorage.sdcard);
    });

    testWidgets('a stalled device drain reads as one recording: copied pieces and the rest on the device', (
      tester,
    ) async {
      final rest = Wal(
        timerStart: _baseSeconds + 300,
        codec: BleAudioCodec.opus,
        seconds: 300,
        status: WalStatus.miss,
        storage: WalStorage.flashPage,
        device: 'pendant',
      );
      Wal piece(int start) => Wal(
            timerStart: start,
            codec: BleAudioCodec.opus,
            seconds: 150,
            status: WalStatus.miss,
            storage: WalStorage.disk,
            originalStorage: WalStorage.flashPage,
            device: 'pendant',
          );
      await _pumpPage(tester, _FakeSync(wals: [rest, piece(_baseSeconds), piece(_baseSeconds + 150)]));
      expect(find.text('1 recording · 10m on the way'), findsOneWidget);
    });

    test('the catching-up check is answered once per WAL list, not per progress tick', () {
      final wals = [_wal('long', 40, WalStatus.miss)];
      final sync = _FakeSync(wals: wals);
      expect(SyncPendingWork.isLargeBacklog(sync), isTrue);
      // Same list, same answer, even though nothing re-scans it.
      wals.first.seconds = 60;
      expect(SyncPendingWork.isLargeBacklog(sync), isTrue);
      // A new list, as SyncProvider publishes on any status change, is read afresh.
      expect(SyncPendingWork.isLargeBacklog(_FakeSync(wals: [...wals])), isFalse);
    });

    test('a device drain counts its audio once toward catching up', () {
      final source = Wal(
        timerStart: _baseSeconds,
        codec: BleAudioCodec.opus,
        seconds: 20 * 60,
        status: WalStatus.miss,
        storage: WalStorage.sdcard,
        device: 'pendant',
      );
      final copied = Wal(
        timerStart: _baseSeconds,
        codec: BleAudioCodec.opus,
        seconds: 15 * 60,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        originalStorage: WalStorage.sdcard,
        device: 'pendant',
      );
      expect(SyncPendingWork.isLargeBacklog(_FakeSync(wals: [source, copied])), isFalse);
    });

    testWidgets('keeps refused recordings one tap away, on the Sync Details row', (tester) async {
      await _pumpPage(
        tester,
        _FakeSync(wals: [_wal('ready', 5, WalStatus.miss), _wal('too-old', 3, WalStatus.outsideRecoveryWindow)]),
      );
      expect(find.text('1 recording need attention'), findsOneWidget);
    });

    testWidgets('Sync Details opens the Offline Sync page the device settings open', (tester) async {
      await _pumpPage(
        tester,
        _FakeSync(wals: [_wal('processing', 4, WalStatus.uploaded)]),
        extras: [
          ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
          ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device()),
        ],
      );
      await tester.tap(find.byKey(const Key('on_the_way_sync_details')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('Offline Sync'), findsWidgets);
    });

    testWidgets('Sync Details shows the v2 alert when device-resident work has no storage support', (tester) async {
      final device = _wal('device', 2, WalStatus.miss)..storage = WalStorage.sdcard;
      await _pumpPage(
        tester,
        _FakeSync(wals: [device]),
        extras: [
          ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
          ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device(storageSupport: false)),
        ],
      );
      await tester.tap(find.byKey(const Key('on_the_way_sync_details')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('Offline Sync unavailable'), findsOneWidget);
    });

    testWidgets('refused recordings alone are never reported as all synced', (tester) async {
      await _pumpPage(tester, _FakeSync(wals: [_wal('too-old', 3, WalStatus.outsideRecoveryWindow)]));
      expect(find.text('All recordings are synced'), findsNothing);
      expect(find.text('1 recording need attention'), findsOneWidget);
    });

    testWidgets('a sync with no recording listed yet still reads as in progress', (tester) async {
      await _pumpPage(tester, _FakeSync(fetching: true));
      expect(find.text('All recordings are synced'), findsNothing);
      expect(find.text('Transcribing…'), findsOneWidget);
    });

    testWidgets('a live capture still processing is listed once, not again as its uploaded audio', (tester) async {
      final now = DateTime.fromMillisecondsSinceEpoch((_baseSeconds + 60) * 1000);
      final conversations = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
        isSignedIn: () => true,
      )..processingConversations = [
          ServerConversation(
            id: 'conv-1',
            createdAt: now,
            startedAt: now,
            structured: Structured('', ''),
            status: ConversationStatus.processing,
          ),
        ];
      final uploaded = _wal('live', 4, WalStatus.uploaded)..conversationId = 'conv-1';
      await _pumpPage(
        tester,
        _FakeSync(wals: [uploaded]),
        extras: [ChangeNotifierProvider<ConversationProvider>.value(value: conversations)],
      );
      expect(find.text('Processing'), findsOneWidget);
      expect(find.text('Transcribing…'), findsNothing);
    });

    testWidgets('a live capture still processing is not repeated as its not-yet-uploaded audio', (tester) async {
      final now = DateTime.fromMillisecondsSinceEpoch((_baseSeconds + 60) * 1000);
      final conversations = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
        isSignedIn: () => true,
      )..processingConversations = [
          ServerConversation(
            id: 'conv-2',
            createdAt: now,
            startedAt: now,
            structured: Structured('', ''),
            status: ConversationStatus.processing,
          ),
        ];
      final safety = _wal('safety', 4, WalStatus.miss)..conversationId = 'conv-2';
      await _pumpPage(
        tester,
        _FakeSync(wals: [safety]),
        extras: [ChangeNotifierProvider<ConversationProvider>.value(value: conversations)],
      );
      expect(find.text('Processing'), findsOneWidget);
      expect(find.text('Waiting to sync'), findsNothing);
    });

    testWidgets('one recording straddling an upload batch is listed once, by its least advanced part', (tester) async {
      final done = Wal(
        timerStart: _baseSeconds,
        codec: BleAudioCodec.opus,
        seconds: 300,
        status: WalStatus.uploaded,
        device: 'pendant',
      );
      final next = Wal(
        timerStart: _baseSeconds + 300,
        codec: BleAudioCodec.opus,
        seconds: 120,
        status: WalStatus.miss,
        device: 'pendant',
      );
      await _pumpPage(tester, _FakeSync(wals: [next, done]));
      expect(find.text('Transcribing…'), findsNothing);
      expect(find.text('Waiting to sync'), findsOneWidget);
    });

    testWidgets('a transfer with no recording listed yet still reads as in progress', (tester) async {
      await _pumpPage(tester, _FakeSync(syncing: true));
      expect(find.text('Downloading from your device'), findsOneWidget);
    });

    testWidgets('says so when everything has landed', (tester) async {
      await _pumpPage(tester, _FakeSync(wals: [_wal('done', 15, WalStatus.synced)]));
      expect(find.text('All recordings are synced'), findsOneWidget);
    });
  });

  // Home's order holds from the first frame: Daily Recaps, then Today (the pending row first in it),
  // then the rest. Before the list loads, the row opens Today exactly where the list's Today lands.
  group('Home without a catch-up row', () {
    final now = DateTime.now();
    DateTime at(int daysAgo, int hour) => DateTime(now.year, now.month, now.day - daysAgo, hour);
    ServerConversation convo(String id, DateTime when) => ServerConversation(
          id: id,
          createdAt: when,
          startedAt: when,
          finishedAt: when.add(const Duration(minutes: 5)),
          structured: Structured('Conversation $id', 'Overview', emoji: '🙂', category: 'work'),
          status: ConversationStatus.completed,
        );
    // Dated three days back so its card never reads "Today" or "Yesterday".
    Future<({List<DailySummary> items, bool ok})> recaps() async => (
          items: [
            DailySummary(
              id: 'r1',
              date: at(3, 0).toIso8601String().substring(0, 10),
              createdAt: at(2, 4),
              headline: 'Dashboards and paperwork',
              overview: 'A day of dashboards and forms.',
              stats: DayStats(totalConversations: 6, actionItemsCount: 2),
            ),
          ],
          ok: true,
        );
    SyncProvider pending() => _FakeSync(wals: [_wal('processing', 4, WalStatus.uploaded)]);

    Future<ConversationProvider> pumpHome(
      WidgetTester tester,
      SyncProvider sync, {
      List<ServerConversation> items = const [],
      bool loading = false,
      DateTime? start,
      DateTime? end,
    }) async {
      tester.view.physicalSize = const Size(390, 2000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final provider =
          ConversationProvider(conversationListFetcher: () async => (items: items, ok: true), isSignedIn: () => true)
            ..conversations = [...items]
            ..isLoadingConversations = loading
            ..selectedStartDate = start
            ..selectedEndDate = end
            ..groupConversationsByDate();
      final screen = await tester.runAsync(
        () => buildTypedConversationScreen(provider, sync: sync, loadRecaps: recaps),
      );
      await tester.pumpWidget(screen!);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      return provider;
    }

    Future<void> unmount(WidgetTester tester, ConversationProvider provider) async {
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 1));
      provider.dispose();
    }

    void expectTopToBottom(WidgetTester tester, List<Finder> order) {
      for (var i = 0; i + 1 < order.length; i++) {
        expect(
          tester.getRect(order[i]).bottom,
          lessThanOrEqualTo(tester.getRect(order[i + 1]).top),
          reason: '${order[i]} must sit above ${order[i + 1]}',
        );
      }
    }

    final recapsRow = find.byType(HomeDailyRecaps);
    final today = find.text('Today');
    final yesterday = find.text('Yesterday');

    final cases = <String, SyncProvider>{
      'idle': _FakeSync(),
      'small backlog': _FakeSync(wals: [_wal('small', 4, WalStatus.miss)]),
      'large backlog': _FakeSync(wals: [_wal('large', 180, WalStatus.miss)]),
      'downloading': _FakeSync(wals: [_wal('download', 180, WalStatus.miss)], syncing: true),
      'uploaded': pending(),
      'fetching conversations': _FakeSync(fetching: true),
      'fetching after upload': _FakeSync(fetchingWithUploadPhase: true),
      'terminal failure': _FakeSync(wals: [_wal('failed', 10, WalStatus.miss)..retryCount = 99]),
      'local only': _FakeSync(wals: [_wal('local', 10, WalStatus.miss)..onDeviceOnly = true]),
    };
    for (final entry in cases.entries) {
      for (final loading in [false, true]) {
        testWidgets('${entry.key}, loading=$loading: no pending row or artificial Today header', (tester) async {
          final provider =
              await pumpHome(tester, entry.value, loading: loading, items: loading ? [] : [convo('y1', at(1, 18))]);
          expect(find.byKey(_row), findsNothing);
          expect(find.text('Catching up on earlier audio'), findsNothing);
          expect(find.text('Conversations on the way'), findsNothing);
          if (!loading) {
            expect(today, findsNothing);
            expectTopToBottom(tester, [recapsRow, yesterday, find.text('Conversation y1')]);
          }
          await unmount(tester, provider);
        });
      }
    }

    testWidgets('today starts with its conversation, below the recaps', (tester) async {
      final provider = await pumpHome(tester, pending(), items: [convo('t1', at(0, 0)), convo('y1', at(1, 18))]);
      expect(find.byKey(_row), findsNothing);
      expect(today, findsOneWidget);
      expectTopToBottom(tester, [recapsRow, today, find.text('Conversation t1'), yesterday]);
      await unmount(tester, provider);
    });

    testWidgets('a new account keeps its hero without a pending row', (tester) async {
      final provider = await pumpHome(tester, pending());
      expect(find.byKey(_row), findsNothing);
      expect(today, findsNothing);
      expect(find.byType(NoConversationsHero), findsOneWidget);
      await unmount(tester, provider);
    });
  });
}
