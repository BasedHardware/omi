// The Conversations tab before the UI program: rows, the long-press selection mode, swipe to
// delete, and Offline Sync. Grouped capture rows and Daily Recaps did not exist yet.
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';

import '../../../harness.dart';
import '../fakes.dart';

const _page = 'lib/pages/conversations/conversations_page.dart (ConversationsPage)';

final conversationsScenarios = <AuditScenario>[
  AuditScenario(
    id: 'conversations-list',
    title: 'Conversations list, long-press selection and swipe to delete',
    page: _page,
    state: 'Three conversations on one day: a titled one, an untitled one and a discarded one; discarded shown',
    prefs: {'showGoalTrackerEnabled': false, 'showDiscardedMemories': true},
    run: (a) async {
      final items = [
        auditConversation('a', title: 'Design catch-up with Alex'),
        ServerConversation(id: 'b', createdAt: DateTime(2026, 9, 20, 10), structured: Structured('   ', 'Overview')),
        auditConversation('c', title: 'Old planning notes', discarded: true),
      ];
      final provider = ConversationProvider(
        conversationListFetcher: () async => (items: items, ok: true),
        isSignedIn: () => true,
      )
        ..conversationDeleteFetcherOverride = ((_) async => true)
        ..conversations = items
        ..groupConversationsByDate();
      await a.pump(const ConversationsPage(requestInitialLoad: false), providers: <SingleChildWidget>[
        ChangeNotifierProvider<ConversationProvider>.value(value: provider),
        ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
      ]);
      expect(find.byType(ConversationListItem), findsNWidgets(3));
      await a.shot('Conversations tab with a titled, an untitled and a discarded row', step: 'list');
      // No row menu at this revision: a long press selects the row for merging.
      await a.longPress(find.byType(ConversationListItem).first);
      expect(provider.isSelectionModeActive, isTrue);
      await a.shot('Long-press the first row: it is selected for merging (no row menu yet)', step: 'row-menu');

      provider.exitSelectionMode();
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
