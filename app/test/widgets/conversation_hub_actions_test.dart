import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/capture_group.dart';
import 'package:omi/pages/conversation_detail/capture_group_separation.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/conversation_actions.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/date_filter_chip.dart';
import 'package:omi/pages/conversations/widgets/date_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';

ServerConversation _conversation(
  String id, {
  String title = 'Standup notes',
  bool discarded = false,
  DateTime? startedAt,
  DateTime? finishedAt,
}) {
  return ServerConversation(
    id: id,
    createdAt: DateTime(2026, 9, 20, 10),
    startedAt: startedAt,
    finishedAt: finishedAt,
    structured: Structured(title, 'Overview'),
    status: ConversationStatus.completed,
    discarded: discarded,
  );
}

void main() {
  late List<String> deleted;
  late ConversationProvider provider;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    deleted = [];
    provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    provider.conversationDeleteFetcherOverride = (id) async {
      deleted.add(id);
      return true;
    };
  });

  tearDown(() => provider.dispose());

  Future<void> pump(WidgetTester tester, Widget child) {
    return tester.pumpWidget(
      ChangeNotifierProvider<ConversationProvider>.value(
        value: provider,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: child),
        ),
      ),
    );
  }

  Widget deleteButton(List<ServerConversation> conversations) => Builder(
        builder: (context) => TextButton(
          onPressed: () => deleteConversationsWithUndo(context, conversations),
          child: const Center(child: Text('delete')),
        ),
      );

  group('delete with Undo (D5)', () {
    testWidgets('Undo restores the conversation and nothing is deleted on the server', (tester) async {
      final a = _conversation('a');
      provider.conversations = [a];
      await pump(tester, deleteButton([a]));

      await tester.tap(find.text('delete'));
      await tester.pumpAndSettle();
      expect(provider.conversations, isEmpty);
      expect(find.text('Conversation deleted'), findsOneWidget);

      await tester.tap(find.text('Undo'));
      await tester.pumpAndSettle();

      expect(provider.conversations.map((c) => c.id), ['a']);
      await tester.pump(const Duration(seconds: 10));
      expect(deleted, isEmpty);
    });

    testWidgets('the delete is sent when the toast times out', (tester) async {
      final a = _conversation('a');
      provider.conversations = [a];
      await pump(tester, deleteButton([a]));

      await tester.tap(find.text('delete'));
      await tester.pumpAndSettle();
      await tester.pump(OmiFeedbackTiming.undo);
      await tester.pumpAndSettle();

      // The toast closed without Undo, before the provider's own window ran out.
      expect(deleted, ['a']);
    });

    testWidgets('a bulk delete shows one toast that counts and restores them all', (tester) async {
      final a = _conversation('a');
      final b = _conversation('b');
      provider.conversations = [a, b];
      await pump(tester, deleteButton([a, b]));

      await tester.tap(find.text('delete'));
      await tester.pumpAndSettle();
      expect(find.text('2 conversations deleted'), findsOneWidget);

      await tester.tap(find.text('Undo'));
      await tester.pumpAndSettle();
      expect(provider.conversations.map((c) => c.id).toSet(), {'a', 'b'});
    });
  });

  testWidgets('long-press opens one context menu with multi-select as an entry', (tester) async {
    final a = _conversation('a');
    provider.conversations = [a];
    await pump(tester, ConversationListItem(conversation: a, date: DateTime(2026, 9, 20), conversationIdx: 0));

    await tester.longPress(find.byType(ConversationListItem));
    await tester.pumpAndSettle();

    const groupedOnly = {ConversationRowAction.recordings, ConversationRowAction.separate};
    for (final action in ConversationRowAction.values) {
      expect(
        find.byKey(ValueKey('conversation_action_${action.name}')),
        groupedOnly.contains(action) ? findsNothing : findsOneWidget,
        reason: action.name,
      );
    }
    expect(provider.isSelectionModeActive, isFalse);

    await tester.tap(find.byKey(const ValueKey('conversation_action_select')));
    await tester.pumpAndSettle();
    expect(provider.isSelectionModeActive, isTrue);
    expect(provider.isConversationSelected('a'), isTrue);
  });

  testWidgets('a row for an event several devices recorded offers Recordings and Separate…', (tester) async {
    final grouped = ServerConversation(
      id: 'a',
      createdAt: DateTime(2026, 9, 20, 10),
      structured: Structured('Design review', 'Overview'),
      status: ConversationStatus.completed,
      captureGroup: const CaptureGroup(
        id: 'event-1',
        primaryId: 'a',
        members: [CaptureGroupMember(id: 'a', source: 'desktop'), CaptureGroupMember(id: 'b', source: 'omi')],
      ),
    );
    provider.conversations = [grouped];
    await pump(tester, ConversationListItem(conversation: grouped, date: DateTime(2026, 9, 20), conversationIdx: 0));

    await tester.longPress(find.byType(ConversationListItem));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('conversation_action_recordings')), findsOneWidget);
    expect(find.byKey(const ValueKey('conversation_action_separate')), findsOneWidget);

    // One other recording: Separate… goes straight to the page's confirmation, naming the pendant.
    await tester.tap(find.byKey(const ValueKey('conversation_action_separate')));
    await tester.pumpAndSettle();
    expect(find.text('Separate this recording?'), findsOneWidget);
    expect(find.textContaining('Pendant'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
  });

  testWidgets('Separate… from a grouped row separates on confirm and reloads the list', (tester) async {
    final separated = <String>[];
    rowSeparationController = () => CaptureGroupSeparationController(separate: (id) async {
          separated.add(id);
          return CaptureGroupSeparationResult.separated;
        });
    addTearDown(() => rowSeparationController = CaptureGroupSeparationController.new);
    final grouped = ServerConversation(
      id: 'a',
      createdAt: DateTime(2026, 9, 20, 10),
      structured: Structured('Design review', 'Overview'),
      status: ConversationStatus.completed,
      captureGroup: const CaptureGroup(
        id: 'event-1',
        primaryId: 'a',
        members: [CaptureGroupMember(id: 'a', source: 'desktop'), CaptureGroupMember(id: 'b', source: 'omi')],
      ),
    );
    provider.conversations = [grouped];
    await pump(tester, ConversationListItem(conversation: grouped, date: DateTime(2026, 9, 20), conversationIdx: 0));
    await tester.longPress(find.byType(ConversationListItem));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('conversation_action_separate')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Separate').last);
    await tester.pumpAndSettle();
    expect(separated, ['b'], reason: 'the other recording, never the row itself');
  });

  testWidgets('Share on a private row asks before making it public', (tester) async {
    final a = _conversation('a');
    provider.conversations = [a];
    await pump(tester, ConversationListItem(conversation: a, date: DateTime(2026, 9, 20), conversationIdx: 0));
    await tester.longPress(find.byType(ConversationListItem));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('conversation_action_share')));
    await tester.pumpAndSettle();
    expect(find.text('Anyone with the link can view'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(a.visibility, isNot(ConversationVisibility.shared));
  });

  group('row titles (hub audit #21)', () {
    testWidgets('a blank title reads Untitled Conversation; a discarded one says so with its length', (tester) async {
      late BuildContext captured;
      await pump(tester, Builder(builder: (context) => (captured = context, const SizedBox()).$2));

      expect(conversationRowTitle(captured, _conversation('a', title: '  ')), 'Untitled Conversation');
      final start = DateTime(2026, 9, 20, 10);
      final discarded = _conversation(
        'b',
        discarded: true,
        startedAt: start,
        finishedAt: start.add(const Duration(seconds: 12)),
      );
      expect(conversationRowTitle(captured, discarded), 'Discarded · 12s');
    });
  });

  testWidgets('today gets a day header (hub audit #16)', (tester) async {
    await pump(tester, DateListItem(date: DateTime.now(), isFirst: true));
    expect(find.text('Today'), findsOneWidget);
  });

  testWidgets('the active date filter is a removable chip (hub audit #23)', (tester) async {
    await pump(tester, const ConversationDateFilterChip());
    expect(find.byKey(const Key('conversation_date_filter_chip')), findsNothing);

    provider.selectedStartDate = DateTime(2026, 9, 1);
    provider.selectedEndDate = DateTime(2026, 9, 7);
    provider.notifyListeners();
    await tester.pump();

    expect(find.text('Sep 1, 2026 – Sep 7, 2026'), findsOneWidget);
    await tester.tap(find.byTooltip('Remove Filter'));
    await tester.pump();
    expect(provider.selectedStartDate, isNull);
    await tester.pumpAndSettle();
  });
}
