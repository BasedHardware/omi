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
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/daily_recaps_page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';

import '../fakes.dart';
import '../harness.dart';

const _page = 'lib/pages/conversations/conversations_page.dart (ConversationsPage)';

/// A real history (from a customer's Offline Sync): capture backs audio up every 75 s and the pendant
/// handed storage over in 3 minute chunks, so each day of recording is dozens of rows.
class _HistorySyncProvider extends InertSyncProvider {
  _HistorySyncProvider() {
    final now = DateTime.now();
    int at(int daysAgo, int hour, int minute) =>
        DateTime(now.year, now.month, now.day - daysAgo, hour, minute).millisecondsSinceEpoch ~/ 1000;
    Wal wal(int start, int seconds, WalStatus status) => Wal(
        timerStart: start,
        codec: BleAudioCodec.opus,
        seconds: seconds,
        status: status,
        storage: WalStorage.disk,
        device: 'pendant');
    // Back to back, each starting where the previous one ended.
    List<Wal> run(int start, List<int> lengths, WalStatus status) {
      var t = start;
      return [
        for (final s in lengths) wal((t += s) - s, s, status),
      ];
    }

    _wals = [
      ...run(at(0, 19, 23), List.filled(6, 75), WalStatus.uploaded),
      ...run(at(41, 15, 39), List.filled(10, 180), WalStatus.outsideRecoveryWindow),
      ...run(at(41, 12, 56), [40, 53, 68, 29, 9, 74, 75, 75, 73, 74, 73, 75], WalStatus.synced),
      ...run(at(43, 19, 55), List.filled(14, 180), WalStatus.synced),
    ]..sort((a, b) => b.timerStart.compareTo(a.timerStart));
  }

  late final List<Wal> _wals;

  @override
  List<Wal> get allWals => _wals;
  @override
  List<Wal> get displaySortedWals => _wals;
  @override
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) => switch (filter) {
        WalDisplayFilter.all => _wals,
        WalDisplayFilter.pending => _wals.where((w) => w.syncDisplayState != WalSyncDisplayState.synced).toList(),
        WalDisplayFilter.synced => _wals.where((w) => w.syncDisplayState == WalSyncDisplayState.synced).toList(),
      };
}

/// A ConversationProvider already holding [items], grouped by date, whose deletes succeed locally.
List<SingleChildWidget> _listProviders(List<ServerConversation> items) {
  final provider =
      ConversationProvider(conversationListFetcher: () async => (items: items, ok: true), isSignedIn: () => true)
        ..conversationDeleteFetcherOverride = ((_) async => true)
        ..conversations = items
        ..groupConversationsByDate();
  return [
    ChangeNotifierProvider<ConversationProvider>.value(value: provider),
    ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
  ];
}

const _twoSourceGroup = CaptureGroup(
  id: 'group-1',
  primaryId: 'grouped-a',
  members: [
    CaptureGroupMember(id: 'grouped-a', source: 'desktop'),
    CaptureGroupMember(id: 'grouped-a-omi', source: 'omi'),
  ],
);

final conversationsScenarios = <AuditScenario>[
  AuditScenario(
    id: 'conversations-locked-preview',
    title: 'Locked conversations with an upgrade action',
    page: _page,
    state: 'An unlocked conversation followed by three consecutive locked previews, which share one '
        'frosted card and one upgrade action; synthetic titles only',
    run: (a) async {
      final items = [
        auditConversation('unlocked', title: 'Design catch-up with Alex'),
        for (var i = 0; i < 3; i++)
          ServerConversation(
            id: 'locked-$i',
            createdAt: DateTime(2026, 9, 20, 10 - i),
            startedAt: DateTime(2026, 9, 20, 10 - i),
            finishedAt: DateTime(2026, 9, 20, 10 - i, 3),
            structured: Structured('Planning the next team meeting', 'Overview', emoji: '📝'),
            isLocked: true,
          ),
      ];
      await a.pump(const ConversationsPage(requestInitialLoad: false), providers: _listProviders(items));
      expect(find.byType(ConversationListItem), findsNWidgets(4));
      expect(find.byType(LockedConversationRun), findsOneWidget);
      expect(find.text('Upgrade to Unlimited'), findsOneWidget);
      await a.shot('Conversation list with frosted locked previews');
    },
  ),
  AuditScenario(
    id: 'conversations-list',
    title: 'Conversations list, row menu and swipe to delete',
    page: _page,
    state: 'Three conversations on one day: a titled one, an untitled one and a discarded one; discarded shown',
    prefs: {'showDiscardedMemories': true},
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
      // long-press recognizer fires, the rest carry the row past the point where it asks.
      final gesture = await a.tester.startGesture(a.tester.getCenter(find.byType(ConversationListItem).first));
      for (var i = 0; i < 6; i++) {
        await gesture.moveBy(const Offset(-60, 0));
        await a.tester.pump(const Duration(milliseconds: 16));
      }
      await gesture.up();
      await a.settle();
      expect(find.text('Delete Conversation'), findsOneWidget);
      await a.shot('Swipe the first row to delete: the confirm menu from its delete button', step: 'swipe-delete');
    },
  ),
  AuditScenario(
    id: 'conversations-grouped-row',
    title: 'Grouped capture row, its Recordings/Separate menu and the Separate confirmation',
    page: _page,
    state: 'One conversation recorded by two sources (desktop and pendant) collapsed into one capture group',
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
        DailyRecapsPage(fetchSummaries: ({int limit = 20, int offset = 0}) async => (items: [summary], ok: true)),
      );
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
    id: 'conversations-offline-sync-history',
    title: 'Offline Sync with a day of recording',
    page: 'lib/pages/conversations/auto_sync_page.dart (AutoSyncPage)',
    state:
        'Six 75 s files uploading today; ten 3 min files too old to sync, twelve 9 s-75 s synced files and fourteen 3 min synced files from about six weeks ago',
    run: (a) async {
      await a.pump(const AutoSyncPage(),
          providers: [ChangeNotifierProvider<SyncProvider>(create: (_) => _HistorySyncProvider())]);
      await a.tap(find.text('All'));
      await a.scrollSeries('Open Offline Sync, choose All and scroll the recordings');
    },
  ),
  AuditScenario(
    id: 'conversations-offline-sync-recording-files',
    title: 'One recording opened to its files',
    page: 'lib/pages/conversations/auto_sync_page.dart (AutoSyncPage)',
    state: 'The history above; the synced 12:56 PM recording (twelve 9 s-75 s files) is tapped',
    run: (a) async {
      await a.pump(const AutoSyncPage(),
          providers: [ChangeNotifierProvider<SyncProvider>(create: (_) => _HistorySyncProvider())]);
      await a.tap(find.text('All'));
      await a.tap(find.textContaining('12:56'));
      await a.shot('Tap a recording to see the files it is made of');
    },
  ),
];
