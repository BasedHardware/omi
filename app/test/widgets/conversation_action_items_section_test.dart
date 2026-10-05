import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_action_items_section.dart';
import 'package:omi/ui/ui.dart';

void main() {
  final l10n = lookupAppLocalizations(const Locale('en'));
  late OmiDateFormat dates;
  setUpAll(() async {
    await initializeDateFormatting();
    dates = OmiDateFormat(
      locale: const Locale('en'),
      use24HourFormat: false,
      l10n: l10n,
      clock: () => DateTime(2026, 10, 5, 12),
    );
  });

  group('ActionItemMeta', () {
    test('the mobile adapter round-trips due certainty and action-item targets', () {
      final item = ActionItem.fromJson({
        'description': 'Send the proposal',
        'due_certainty': 'tentative',
        'target_task_id': 'task-7',
        'source_segment_ids': ['segment-4'],
      });
      expect(item.dueCertainty, 'tentative');
      expect(item.targetTaskId, 'task-7');
      expect(item.sourceSegmentIds, ['segment-4']);
      expect(item.toJson()['due_certainty'], 'tentative');
      expect(item.toJson()['target_task_id'], 'task-7');
      expect(item.toJson()['source_segment_ids'], ['segment-4']);
    });

    test('an item with no owner, due date or context has no metadata, never "Unknown"', () {
      final meta = ActionItemMeta.of(ActionItem('Send the deck'), l10n: l10n, dates: dates);
      expect(meta.owner, isNull);
      expect(meta.due, isNull);
      expect(meta.context, isNull);
      expect(meta.hasOwnerOrDue, isFalse);
    });

    test('the reader\'s own item is "You"; another owner keeps their name', () {
      final mine = ActionItem('Send the deck', captureOwner: 'user', ownerName: 'David');
      final theirs = ActionItem('Share the provider info', captureOwner: 'other', ownerName: 'Eddie Thai');
      expect(ActionItemMeta.of(mine, l10n: l10n, dates: dates).owner, 'You');
      expect(ActionItemMeta.of(theirs, l10n: l10n, dates: dates).owner, 'Eddie Thai');
    });

    test('a blank or email-shaped owner name is left out', () {
      for (final name in ['  ', 'eddie@example.com']) {
        final meta = ActionItemMeta.of(ActionItem('x', ownerName: name), l10n: l10n, dates: dates);
        expect(meta.owner, isNull, reason: name);
      }
    });

    test('due date reads as a local day; context is trimmed', () {
      final item = ActionItem('x', dueAt: DateTime(2026, 10, 7, 9), context: '  Eddie will forward it. ');
      final meta = ActionItemMeta.of(item, l10n: l10n, dates: dates);
      expect(meta.due, 'Due Wed, Oct 7');
      expect(meta.context, 'Eddie will forward it.');
      expect(ActionItemMeta.of(ActionItem('x', dueAt: DateTime(2026, 10, 5, 18)), l10n: l10n, dates: dates).due,
          'Due Today');
    });

    test('tentative deadline includes the marker and accessible wording', () {
      final item = ActionItem('x', dueAt: DateTime(2026, 10, 7, 9), dueCertainty: 'tentative');
      final meta = ActionItemMeta.of(item, l10n: l10n, dates: dates);
      expect(meta.due, 'Due ~Wed, Oct 7');
      expect(meta.dueAccessibility, 'Tentatively due Wed, Oct 7');
    });
  });

  group('ConversationActionItemsSection', () {
    Future<void> pump(WidgetTester tester, List<ActionItem> items) async {
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: CustomScrollView(
            slivers: [
              ConversationActionItemsSection(
                items: items,
                conversationId: 'conversation-1',
                onShowInTranscript: (_) {},
              ),
            ],
          ),
        ),
      ));
    }

    testWidgets('is absent when every item is deleted', (tester) async {
      await pump(tester, [ActionItem('gone', deleted: true)]);
      expect(find.byKey(const ValueKey('conversation_action_items_section')), findsNothing);
    });

    testWidgets('shows owner, due and context, and no "Unknown" placeholder', (tester) async {
      await pump(tester, [
        ActionItem(
          'Share the wind-down provider information with David.',
          captureOwner: 'other',
          ownerName: 'Eddie Thai',
          context: 'Eddie said they would follow up about Simple Closure.',
        ),
        ActionItem('Send investors an update on the wind-down plan.', captureOwner: 'user'),
        ActionItem('Something with no metadata at all.'),
      ]);
      expect(find.text('Action items'), findsOneWidget);
      expect(find.text('Eddie Thai'), findsOneWidget);
      expect(find.text('ET'), findsOneWidget);
      expect(find.text('Eddie said they would follow up about Simple Closure.'), findsOneWidget);
      expect(find.text('You'), findsOneWidget);
      expect(find.textContaining('Unknown'), findsNothing);
      expect(find.textContaining('Due'), findsNothing);
    });

    testWidgets('row menu offers both task and transcript actions and row controls are addressable', (tester) async {
      await pump(tester, [
        ActionItem('Send the proposal', sourceSegmentIds: const ['seg-1'])
      ]);
      expect(find.byKey(const ValueKey('conversation_action_items_section')), findsOneWidget);
      expect(find.byKey(Key('conversation-action-item-toggle-${'Send the proposal'.hashCode}')), findsOneWidget);
      await tester.longPress(find.text('Send the proposal'));
      await tester.pumpAndSettle();
      expect(find.text('Add to Tasks'), findsOneWidget);
      expect(find.text('Show in Transcript'), findsOneWidget);
    });
  });

  group('ConversationActionItemTaskSession', () {
    test('check, uncheck, and recheck reuse exactly one completed task', () async {
      final createdStates = <bool>[];
      final taskUpdates = <(String, bool)>[];
      final itemUpdates = <(int, bool)>[];
      final idempotencyKeys = <String>[];
      final session = ConversationActionItemTaskSession(
        newIdempotencyKey: () => 'stable-key',
        createTask: (item, {required completed, required idempotencyKey}) async {
          createdStates.add(completed);
          idempotencyKeys.add(idempotencyKey);
          return 'task-1';
        },
        updateTask: (id, completed) async {
          taskUpdates.add((id, completed));
          return true;
        },
        updateConversationItem: (index, completed) async {
          itemUpdates.add((index, completed));
          return true;
        },
      );
      final item = ActionItem('Send the proposal', sourceSegmentIds: const ['segment-1']);

      expect(await session.setCompleted(item, 0, true), isTrue);
      expect(await session.setCompleted(item, 0, false), isTrue);
      expect(await session.setCompleted(item, 0, true), isTrue);

      expect(createdStates, [true]);
      expect(taskUpdates, [('task-1', false), ('task-1', true)]);
      expect(itemUpdates, [(0, true), (0, false), (0, true)]);
      expect(idempotencyKeys, ['stable-key']);
    });

    test('Add to Tasks creates one open task even when selected repeatedly', () async {
      final createdStates = <bool>[];
      final session = ConversationActionItemTaskSession(
        newIdempotencyKey: () => 'stable-key',
        createTask: (item, {required completed, required idempotencyKey}) async {
          createdStates.add(completed);
          return 'task-1';
        },
        updateTask: (_, __) async => true,
        updateConversationItem: (_, __) async => true,
      );
      final item = ActionItem('Send the proposal');

      expect(await session.addToTasks(item), isTrue);
      expect(await session.addToTasks(item), isTrue);
      expect(createdStates, [false]);
    });
  });
}
