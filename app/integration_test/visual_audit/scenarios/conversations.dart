// The Conversations tab: rows, the row menu, swipe to delete, grouped capture rows, Daily Recaps
// and Offline Sync.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/schema/capture_group.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/daily_recaps_page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';

import '../fakes.dart';
import '../harness.dart';

const _page = 'lib/pages/conversations/conversations_page.dart (ConversationsPage)';

/// A ConversationProvider already holding [items], grouped by date, whose deletes succeed locally.
List<SingleChildWidget> _listProviders(List<ServerConversation> items) {
  final provider = ConversationProvider(
    conversationListFetcher: () async => (items: items, ok: true),
    isSignedIn: () => true,
  )
    ..conversationDeleteFetcherOverride = ((_) async => true)
    ..conversations = items
    ..groupConversationsByDate();
  return [
    ChangeNotifierProvider<ConversationProvider>.value(value: provider),
    ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
  ];
}

const _twoSourceGroup = CaptureGroup(id: 'group-1', primaryId: 'grouped-a', members: [
  CaptureGroupMember(id: 'grouped-a', source: 'desktop'),
  CaptureGroupMember(id: 'grouped-a-omi', source: 'omi'),
]);

final conversationsScenarios = <AuditScenario>[
  AuditScenario(
    id: 'conversations-list',
    title: 'Conversations list, row menu and swipe to delete',
    page: _page,
    state: 'Three conversations on one day: a titled one, an untitled one and a discarded one; discarded shown',
    prefs: {'showGoalTrackerEnabled': false, 'showDiscardedMemories': true},
    run: (a) async {
      final items = [
        auditConversation('a', title: 'Design catch-up with Alex'),
        ServerConversation(id: 'b', createdAt: DateTime(2026, 9, 20, 10), structured: Structured('   ', 'Overview')),
        auditConversation('c', title: 'Old planning notes', discarded: true),
      ];
      await a.pump(const ConversationsPage(requestInitialLoad: false), providers: _listProviders(items));
      expect(find.byType(ConversationListItem), findsNWidgets(3));
      await a.shot('Conversations tab with a titled, an untitled and a discarded row', step: 'list');
      await a.longPress(find.byType(ConversationListItem).first);
      await a.shot('Long-press the first row', step: 'row-menu');

      globalNavigatorKey.currentState!.pop();
      await a.settle();
      // A raw gesture in steps: the first move claims the horizontal drag before the row's
      // long-press recognizer fires, the rest carry the row past the dismiss threshold.
      final gesture = await a.tester.startGesture(a.tester.getCenter(find.byType(ConversationListItem).first));
      for (var i = 0; i < 6; i++) {
        await gesture.moveBy(const Offset(-60, 0));
        await a.tester.pump(const Duration(milliseconds: 16));
      }
      await gesture.up();
      await a.settle();
      expect(find.text('Delete Conversation?'), findsOneWidget);
      await a.shot('Swipe the first row to delete: the delete confirmation', step: 'swipe-delete');
    },
  ),
  AuditScenario(
    id: 'conversations-source-filter',
    title: 'Source chips: All, Starred, Pendant, Glasses, Phone, Imported',
    page: _page,
    state: 'Three conversations on one day from the pendant, the phone and glasses',
    prefs: {'showGoalTrackerEnabled': false},
    run: (a) async {
      ServerConversation from(String id, String title, ConversationSource source, int hour) => ServerConversation(
            id: id,
            createdAt: DateTime(2026, 9, 20, hour),
            structured: Structured(title, 'Overview', emoji: '', category: 'work'),
            status: ConversationStatus.completed,
            source: source,
          );
      final items = [
        from('p', 'Call Chitapa reminder', ConversationSource.omi, 15),
        from('h', 'Subscription concerns', ConversationSource.phone, 14),
        from('g', 'Pricing review', ConversationSource.openglass, 11),
      ];
      await a.pump(const ConversationsPage(requestInitialLoad: false), providers: _listProviders(items));
      expect(find.byKey(const ValueKey('conversation_source_glasses')), findsOneWidget);
      await a.shot('All conversations, with the source chips after Starred', step: 'all');
      await a.tap(find.byKey(const ValueKey('conversation_source_glasses')));
      expect(find.byType(ConversationListItem), findsOneWidget);
      await a.shot('Tap Glasses: only conversations recorded by glasses', step: 'glasses');
    },
  ),
  AuditScenario(
    id: 'conversations-grouped-row',
    title: 'Grouped capture row, its Recordings/Separate menu and the Separate confirmation',
    page: _page,
    state: 'One conversation recorded by two sources (desktop and pendant) collapsed into one capture group',
    prefs: {'showGoalTrackerEnabled': false},
    run: (a) async {
      final grouped = auditConversation('grouped-a', title: 'Standup with the team', captureGroup: _twoSourceGroup);
      await a.pump(const ConversationsPage(requestInitialLoad: false), providers: _listProviders([grouped]));
      await a.shot('One row for the two-source capture group, with capture-source icons', step: 'list');
      await a.longPress(find.byType(ConversationListItem).first);
      expect(find.byKey(const ValueKey('conversation_action_separate')), findsOneWidget);
      await a.shot('Long-press the grouped row: the menu offers Recordings and Separate', step: 'row-menu');
      await a.tap(find.byKey(const ValueKey('conversation_action_separate')));
      await a.shot('Tap Separate: a two-member group goes straight to the confirmation', step: 'separate-confirm');
    },
  ),
  AuditScenario(
    id: 'conversations-daily-recaps',
    title: 'Daily Recaps',
    page: 'lib/pages/conversations/daily_recaps_page.dart (DailyRecapsPage)',
    state: 'An injected fetcher returning one daily recap for 2026-09-20',
    run: (a) async {
      final summary = DailySummary(
        id: 'summary-1',
        date: '2026-09-20',
        createdAt: DateTime.utc(2026, 9, 20, 12),
        headline: 'A quiet day',
        overview: 'Nothing much happened',
        stats: DayStats(totalConversations: 5, actionItemsCount: 3),
      );
      await a.pump(
          DailyRecapsPage(fetchSummaries: ({int limit = 20, int offset = 0}) async => (items: [summary], ok: true)));
      await a.shot('Open Daily Recaps');
    },
  ),
  AuditScenario(
    id: 'conversations-offline-sync',
    title: 'Offline Sync with nothing pending',
    page: 'lib/pages/conversations/auto_sync_page.dart (AutoSyncPage)',
    state: 'Inert SyncProvider with no recordings; no device connected',
    run: (a) async {
      await a.pump(const AutoSyncPage());
      await a.shot('Open Offline Sync with no pending recordings');
    },
  ),
  AuditScenario(
    id: 'conversations-offline-sync-pending',
    title: 'Offline Sync with recordings waiting, one failed, and two synced',
    page: 'lib/pages/conversations/auto_sync_page.dart (AutoSyncPage)',
    state: 'A connected Omi pendant; four offline recordings (waiting, failed after retries, two synced)',
    run: (a) async {
      int at(int day, int hour, int minute) => DateTime(2026, 9, day, hour, minute).millisecondsSinceEpoch ~/ 1000;
      Wal wal(int start, int seconds, WalStatus status, {int retries = 0, String? conversationId}) => Wal(
            timerStart: start,
            codec: BleAudioCodec.opus,
            seconds: seconds,
            status: status,
            storage: WalStorage.sdcard,
            device: 'omi',
            retryCount: retries,
            conversationId: conversationId,
          );
      final wals = [
        wal(at(20, 11, 20), 18 * 60, WalStatus.miss),
        wal(at(20, 9, 2), 6 * 60, WalStatus.miss, retries: walMaxAutoRetries),
        wal(at(19, 18, 5), 18 * 60, WalStatus.synced, conversationId: 'c1'),
        wal(at(19, 11, 40), 42 * 60, WalStatus.synced, conversationId: 'c2'),
      ];
      final pendant = BtDevice(id: 'D1:A2:B3:C4:D5:E6', name: 'Omi', type: DeviceType.omi, rssi: -40);
      await a.pump(const AutoSyncPage(), providers: [
        ChangeNotifierProvider<SyncProvider>.value(value: _SeededSyncProvider(wals)),
        ChangeNotifierProvider<DeviceProvider>.value(value: AuditDeviceProvider(connected: true, device: pendant)),
      ]);
      await a.shot('Open Offline Sync: the pending recordings first', step: 'pending');
      await a.tap(find.text('All'));
      await a.shot('Tap All: every recording, then Storage', step: 'all');
    },
  ),
];

/// Offline recordings for the Sync page, grouped the way [SyncProvider] groups them.
class _SeededSyncProvider extends InertSyncProvider {
  _SeededSyncProvider(this.wals);

  final List<Wal> wals;

  bool _pending(Wal w) => switch (w.syncDisplayState) {
        WalSyncDisplayState.waiting || WalSyncDisplayState.retrying || WalSyncDisplayState.failed => true,
        _ => false,
      };

  @override
  List<Wal> get allWals => wals;
  @override
  List<Wal> get displaySortedWals => wals;
  @override
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) => switch (filter) {
        WalDisplayFilter.pending => wals.where(_pending).toList(),
        WalDisplayFilter.synced => wals.where((w) => w.syncDisplayState == WalSyncDisplayState.synced).toList(),
        _ => wals,
      };
  @override
  int get needsAttentionWalsCount => wals.where((w) => w.syncDisplayState == WalSyncDisplayState.failed).length;
  @override
  int get clearableWalsCount => wals.length;
  @override
  int get missingWalsInSeconds => wals.where(_pending).fold(0, (sum, w) => sum + w.seconds);
}
