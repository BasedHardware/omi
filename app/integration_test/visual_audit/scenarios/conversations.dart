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
];
