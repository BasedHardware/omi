// Recordings that are not conversations yet, and what Omi did on its own: Home's pending row in
// Today, the On the Way page it opens, the Activity bell in the header and the Activity page.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart' show BleAudioCodec;
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/activity/activity_page.dart';
import 'package:omi/pages/activity/activity_seen.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';

import '../../../fakes.dart';
import '../../../harness.dart';
import 'capture.dart';

/// A SyncProvider reporting one fixed offline-sync pipeline state.
class _SyncAuditProvider extends ChangeNotifier implements SyncProvider {
  _SyncAuditProvider({this.wals = const [], this.phase = SyncPhase.idle});

  final List<Wal> wals;
  final SyncPhase phase;

  @override
  SyncState get syncState =>
      phase == SyncPhase.idle ? const SyncState() : SyncState(status: SyncStatus.syncing, phase: phase);
  @override
  bool get isSyncing => phase != SyncPhase.idle;
  @override
  List<Wal> get allWals => wals;
  @override
  List<Wal> get displaySortedWals => [...wals]..sort((a, b) => b.timerStart.compareTo(a.timerStart));
  @override
  List<Wal> get uploadedWals => wals.where((w) => w.status == WalStatus.uploaded).toList();
  @override
  bool get isRateLimited => false;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

final _now = DateTime.now();
final _today = DateTime(_now.year, _now.month, _now.day);
DateTime _at(int daysAgo, int hour, int minute) => DateTime(_now.year, _now.month, _now.day - daysAgo, hour, minute);

Wal _wal(DateTime start, int minutes, WalStatus status, {WalStorage storage = WalStorage.disk}) => Wal(
      timerStart: start.millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      seconds: minutes * 60,
      status: status,
      storage: storage,
      device: 'pendant',
    );

ServerConversation _convo(String id, String title, String emoji, DateTime at, int minutes) => ServerConversation(
      id: id,
      createdAt: at,
      startedAt: at,
      finishedAt: at.add(Duration(minutes: minutes)),
      structured: Structured(title, 'Overview', emoji: emoji, category: 'work'),
      status: ConversationStatus.completed,
    );

final _recaps = [
  DailySummary(
    id: 'r1',
    date: _today.subtract(const Duration(days: 1)).toIso8601String().substring(0, 10),
    createdAt: _at(0, 4, 10),
    headline: 'Dashboard Clarity Amid Paperwork',
    overview: 'A day of dashboards and forms.',
    dayEmoji: '📊',
    stats: DayStats(totalConversations: 6, actionItemsCount: 2),
  ),
  DailySummary(
    id: 'r2',
    date: _today.subtract(const Duration(days: 2)).toIso8601String().substring(0, 10),
    createdAt: _at(1, 4, 5),
    headline: 'Wind-Down Paperwork and Hardware Reality',
    overview: '',
    dayEmoji: '🔧',
    stats: DayStats(totalConversations: 4, actionItemsCount: 1),
  ),
];

final _todayItems = [
  _convo('h1', 'Trying Something and Discussing Its QR Code', '🍽️', _at(0, 13, 37), 3),
  _convo('h2', 'Dinner, AI Demo Day, and Model Feedback', '🍽️', _at(0, 13, 5), 28),
  _convo('h3', 'Morning Run Notes', '🏃', _at(0, 7, 31), 6),
];

/// Home with [items] (today's three conversations by default), two recaps, and [sync]'s pending
/// work. With [fetch], Home starts empty and loads its list through it, as on a cold start.
Future<void> _runHome(
  AuditRun a,
  SyncProvider sync, {
  List<ServerConversation>? items,
  ConversationListFetcher? fetch,
}) async {
  final list = items ?? _todayItems;
  final conversations = ConversationProvider(
    conversationListFetcher: fetch ?? () async => (items: list, ok: true),
    isSignedIn: () => true,
  );
  if (fetch == null) {
    conversations
      ..conversations = list
      ..groupConversationsByDate();
  }
  await a.pump(
    HomeFrame(recaps: () async => (items: _recaps, ok: true)),
    scaffold: false,
    providers: [
      ChangeNotifierProvider<DeviceProvider>.value(
        value: AuditDeviceProvider(connected: true, battery: 79, device: auditPendant),
      ),
      ChangeNotifierProvider<CaptureProvider>.value(value: AuditCaptureProvider(AuditLive.pendant)),
      ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
      ChangeNotifierProvider<SyncProvider>.value(value: sync),
    ],
  );
}

/// An in-memory bell state: last visit yesterday, so this morning's recap is new.
ActivitySeen _seenYesterday() {
  var stored = _at(1, 20, 0).millisecondsSinceEpoch;
  return ActivitySeen(read: () => stored, write: (v) => stored = v);
}

final _changes = ReviewChangesPage(
  changes: [
    ReviewChange(
      changeId: 'c1',
      kind: ReviewChangeKind.mergeMemories,
      title: 'Merged two memories about your gym schedule',
      createdAt: _at(0, 4, 2),
    ),
    ReviewChange(
      changeId: 'c2',
      kind: ReviewChangeKind.labelSpeaker,
      title: 'Labeled Maya in 2 conversations',
      createdAt: _at(0, 1, 40),
    ),
    ReviewChange(
      changeId: 'c3',
      kind: ReviewChangeKind.closeTask,
      title: 'Closed “Send the deck to Priya”',
      createdAt: _at(1, 16, 12),
    ),
  ],
);

final offlineProcessingScenarios = <AuditScenario>[
  AuditScenario(
    id: 'home-offline-processing',
    title: 'Home: conversations on the way',
    page: 'lib/pages/conversations/widgets/home_pending_row.dart (HomePendingRow) on Home',
    state: 'Two recordings uploaded and transcribing; three conversations today; two recaps',
    run: (a) async {
      final sync = _SyncAuditProvider(
        wals: [_wal(_at(0, 18, 41), 14, WalStatus.uploaded), _wal(_at(0, 17, 58), 3, WalStatus.uploaded)],
      );
      await _runHome(a, sync);
      expect(find.text('Conversations on the way'), findsOneWidget);
      expect(find.text('Transcribing…'), findsOneWidget);
      await a.shot('Home shows one pending row under Today');
    },
  ),
  AuditScenario(
    id: 'home-offline-processing-ready',
    title: 'Home: catching up on a long backlog',
    page: 'lib/pages/conversations/widgets/home_pending_row.dart (HomePendingRow) on Home',
    state: 'Three hours of pendant audio waiting for its sync, one block downloading; the bell has a new recap',
    run: (a) async {
      final sync = _SyncAuditProvider(
        phase: SyncPhase.downloadingFromDevice,
        wals: [
          _wal(_at(0, 15, 0), 70, WalStatus.miss, storage: WalStorage.sdcard),
          _wal(_at(0, 11, 0), 110, WalStatus.miss, storage: WalStorage.sdcard),
        ],
      );
      // Home's recaps report to the app's bell state, so seed that one and put it back after.
      final previous = ActivitySeen.instance;
      ActivitySeen.instance = _seenYesterday();
      addTearDown(() => ActivitySeen.instance = previous);
      await _runHome(a, sync);
      expect(find.byKey(const ValueKey('home_activity_dot')), findsOneWidget);
      expect(find.text('Catching up on earlier audio'), findsOneWidget);
      await a.shot('A long backlog reads as catching up, with no hour count');
    },
  ),
  AuditScenario(
    id: 'home-first-load',
    title: 'Home: first load with conversations on the way',
    page: 'lib/pages/conversations/conversations_page.dart (ConversationsPage) on Home',
    state: 'Cold start: the list loads while two recordings transcribe, then today\'s three conversations '
        'arrive; two recaps',
    run: (a) async {
      final sync = _SyncAuditProvider(
        wals: [_wal(_at(0, 18, 41), 14, WalStatus.uploaded), _wal(_at(0, 17, 58), 3, WalStatus.uploaded)],
      );
      final list = Completer<({List<ServerConversation> items, bool ok})>();
      await _runHome(a, sync, fetch: () => list.future);
      expect(find.text('Conversations on the way'), findsOneWidget);
      expect(find.text('Today'), findsOneWidget);
      await a.shot('Home opens: recaps, then Today with the pending row, then the skeleton', step: 'loading');
      list.complete((items: _todayItems, ok: true));
      await a.settle();
      expect(find.text('Morning Run Notes'), findsOneWidget);
      expect(find.text('Today'), findsOneWidget);
      await a.shot('Today\'s conversations arrive under the pending row', step: 'loaded');
    },
  ),
  AuditScenario(
    id: 'home-pending-none-today',
    title: 'Home: conversations on the way, none yet today',
    page: 'lib/pages/conversations/conversations_page.dart (ConversationsPage) on Home',
    state: 'Two recordings transcribing; two conversations from yesterday and none today; two recaps',
    run: (a) async {
      final sync = _SyncAuditProvider(
        wals: [_wal(_at(0, 9, 12), 14, WalStatus.uploaded), _wal(_at(0, 8, 40), 3, WalStatus.uploaded)],
      );
      await _runHome(
        a,
        sync,
        items: [
          _convo('y1', 'Dinner, AI Demo Day, and Model Feedback', '🍽️', _at(1, 19, 5), 28),
          _convo('y2', 'Morning Run Notes', '🏃', _at(1, 7, 31), 6),
        ],
      );
      expect(find.text('Today'), findsOneWidget);
      await a.shot('The pending row opens Today above Yesterday');
    },
  ),
  AuditScenario(
    id: 'on-the-way',
    title: 'On the Way',
    page: 'lib/pages/conversations/on_the_way_page.dart (OnTheWayPage)',
    state: 'One recording transcribing, one uploading from the phone, one still on the pendant, '
        'and one the server refused',
    run: (a) async {
      final sync = _SyncAuditProvider(
        phase: SyncPhase.uploadingToCloud,
        wals: [
          _wal(_at(0, 18, 41), 14, WalStatus.uploaded),
          _wal(_at(0, 17, 58), 3, WalStatus.miss)..isSyncing = true,
          _wal(_at(0, 17, 40), 1, WalStatus.miss, storage: WalStorage.sdcard),
          _wal(_at(2, 9, 0), 5, WalStatus.outsideRecoveryWindow),
        ],
      );
      await a.pump(
        OnTheWayPage(syncProvider: sync, multiFileSync: true),
        scaffold: false,
        providers: [ChangeNotifierProvider<SyncProvider>.value(value: sync)],
      );
      expect(find.text('On the Way'), findsOneWidget);
      expect(find.text('Sync details'), findsOneWidget);
      await a.shot('Open the pending row');
    },
  ),
  AuditScenario(
    id: 'activity',
    title: 'Activity',
    page: 'lib/pages/activity/activity_page.dart (ActivityPage)',
    state: 'Two recaps (one new since yesterday’s visit) and three changes Omi made on its own',
    run: (a) async {
      await a.pump(
        ActivityPage(
          seen: _seenYesterday(),
          loadRecaps: () async => (items: _recaps, ok: true),
          loadChanges: ({cursor}) async => ApiSuccess(_changes),
          probeDreamReport: () async => false,
        ),
        scaffold: false,
      );
      expect(find.text('Activity'), findsOneWidget);
      expect(find.byKey(const Key('activity_new_dot')), findsOneWidget);
      await a.shot('Open the bell');
    },
  ),
];
