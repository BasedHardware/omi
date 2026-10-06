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
          dueAt: DateTime(2026, 10, 7),
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
      expect(find.text('Due Wed, Oct 7'), findsOneWidget);
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
    ConversationActionItemTaskSession sessionWith({
      required Future<String?> Function(ActionItem item, bool completed, String idempotencyKey) onCreate,
      required Future<bool> Function(String taskId, bool completed) onUpdate,
      required Future<bool> Function(int index, bool completed) onItemUpdate,
      Future<bool> Function(String taskId)? onDelete,
      String Function()? newIdempotencyKey,
      Map<String, String>? persisted,
      Future<Map<String, String>> Function()? readPersistedTaskIds,
      Future<void> Function(Map<String, String>)? writePersistedTaskIds,
    }) =>
        ConversationActionItemTaskSession(
          conversationId: 'conversation-1',
          createTask: (item, {required completed, required idempotencyKey}) async =>
              onCreate(item, completed, idempotencyKey),
          updateTask: (id, completed) async => onUpdate(id, completed),
          updateConversationItem: (index, completed) async => onItemUpdate(index, completed),
          deleteTask: onDelete == null ? null : (id) => onDelete(id),
          newIdempotencyKey: newIdempotencyKey,
          readPersistedTaskIds: readPersistedTaskIds ?? () async => persisted ?? {},
          writePersistedTaskIds: writePersistedTaskIds ?? (_) async {},
        );

    test('check, uncheck, and recheck reuse exactly one completed task', () async {
      final createdStates = <bool>[];
      final taskUpdates = <(String, bool)>[];
      final itemUpdates = <(int, bool)>[];
      final idempotencyKeys = <String>[];
      final session = sessionWith(
        newIdempotencyKey: () => 'stable-key',
        onCreate: (item, completed, idempotencyKey) async {
          createdStates.add(completed);
          idempotencyKeys.add(idempotencyKey);
          return 'task-1';
        },
        onUpdate: (id, completed) async {
          taskUpdates.add((id, completed));
          return true;
        },
        onItemUpdate: (index, completed) async {
          itemUpdates.add((index, completed));
          return true;
        },
      );
      final item = ActionItem('Send the proposal', sourceSegmentIds: const ['segment-1']);

      expect(await session.setCompleted(item, 0, true), 0);
      expect(await session.setCompleted(item, 0, false), 0);
      expect(await session.setCompleted(item, 0, true), 0);

      expect(createdStates, [true]);
      expect(taskUpdates, [('task-1', false), ('task-1', true)]);
      expect(itemUpdates, [(0, true), (0, false), (0, true)]);
      expect(idempotencyKeys, ['stable-key']);
    });

    test('Add to Tasks creates one open task even when selected repeatedly', () async {
      final createdStates = <bool>[];
      final session = sessionWith(
        newIdempotencyKey: () => 'stable-key',
        onCreate: (item, completed, idempotencyKey) async {
          createdStates.add(completed);
          return 'task-1';
        },
        onUpdate: (_, __) async => true,
        onItemUpdate: (_, __) async => true,
      );
      final item = ActionItem('Send the proposal');

      expect(await session.addToTasks(item), isTrue);
      expect(await session.addToTasks(item), isTrue);
      expect(createdStates, [false]);
    });

    test('a fresh session restores the persisted task link and reuses the task', () async {
      // The promoted item's task must survive page sessions: a new session reads
      // the persisted link and updates the same task instead of creating another.
      final stored = <String, String>{};
      final item = ActionItem('Send the proposal', sourceSegmentIds: const ['segment-1']);
      final first = sessionWith(
        newIdempotencyKey: () => 'stable-key',
        onCreate: (item, completed, idempotencyKey) async => 'task-1',
        onUpdate: (_, __) async => true,
        onItemUpdate: (_, __) async => true,
        readPersistedTaskIds: () async => Map.of(stored),
        writePersistedTaskIds: (taskIds) async => stored
          ..clear()
          ..addAll(taskIds),
      );
      await first.setCompleted(item, 0, true, row: 0);
      expect(stored[ConversationActionItemTaskSession.identity(item, row: 0)], 'task-1');

      var creates = 0;
      final taskUpdates = <(String, bool)>[];
      final second = sessionWith(
        onCreate: (item, completed, idempotencyKey) async {
          creates++;
          return 'task-2';
        },
        onUpdate: (id, completed) async {
          taskUpdates.add((id, completed));
          return true;
        },
        onItemUpdate: (_, __) async => true,
        readPersistedTaskIds: () async => Map.of(stored),
      );
      expect(await second.setCompleted(item, 0, false, row: 0), 0);
      expect(creates, 0, reason: 'the restored link must address the existing task');
      expect(taskUpdates, [('task-1', false)]);
    });

    test('a fresh session derives the same deterministic idempotency key', () async {
      // No persisted link yet (the create response was lost): both sessions must
      // send the same key so the backend returns the first task, not a duplicate.
      final item = ActionItem('Send the proposal', sourceSegmentIds: const ['segment-1']);
      final keys = <String>[];
      for (var i = 0; i < 2; i++) {
        final session = sessionWith(
          onCreate: (item, completed, idempotencyKey) async {
            keys.add(idempotencyKey);
            return 'task-$i';
          },
          onUpdate: (_, __) async => true,
          onItemUpdate: (_, __) async => true,
        );
        await session.setCompleted(item, 0, true);
      }
      expect(keys, hasLength(2));
      expect(keys[0], keys[1]);
      expect(keys[0], startsWith('conversation-action-item:'));
    });

    test('two commitments sharing one segment keep separate task identities', () async {
      // One transcript segment can carry several commitments; segment IDs are
      // evidence, not identity. Rows that share evidence must not collide.
      final a = ActionItem('Send the proposal', sourceSegmentIds: const ['seg-1']);
      final b = ActionItem('Follow up with Eddie', sourceSegmentIds: const ['seg-1']);
      expect(ConversationActionItemTaskSession.identity(a), isNot(ConversationActionItemTaskSession.identity(b)));

      // Identical twins are two commitments: the row index disambiguates them.
      final twin = ActionItem(
        'Send the proposal',
        sourceSegmentIds: const ['seg-1'],
      );
      expect(ConversationActionItemTaskSession.identity(a, row: 0),
          isNot(ConversationActionItemTaskSession.identity(twin, row: 1)));
      // Without a row, identity still matches for legacy callers and stable keys.
      expect(ConversationActionItemTaskSession.identity(a), ConversationActionItemTaskSession.identity(twin));
    });

    test('identical twins get separate pending state, tasks and summary rows', () async {
      // The backend allows two identical extracted rows; promoting one must not
      // make the other look added, and each toggle must drive its own task.
      final twin = ActionItem('Send the proposal', sourceSegmentIds: const ['seg-1']);
      final created = <String>[];
      final updates = <(String, bool)>[];
      final patched = <int>[];
      final session = sessionWith(
        // No key override: the production default derives the key from the
        // conversation and the row identity, so twins mint distinct keys.
        onCreate: (item, completed, idempotencyKey) async {
          created.add(idempotencyKey);
          return 'task-${created.length}';
        },
        onUpdate: (id, completed) async {
          updates.add((id, completed));
          return true;
        },
        onItemUpdate: (index, completed) async {
          patched.add(index);
          return true;
        },
      );

      expect(await session.setCompleted(twin, 0, true, row: 0), 0);
      expect(await session.setCompleted(twin, 1, true, row: 1), 1);

      expect(created, hasLength(2), reason: 'each row mints its own task');
      expect(created[0], isNot(created[1]));
      expect(patched, [0, 1]);
      // One row's task never addresses the other's.
      expect(await session.setCompleted(twin, 0, false, row: 0), 0);
      expect(updates, [('task-1', false)]);
    });

    test('a task created for one twin is not reused by its sibling', () async {
      final twin = ActionItem('Send the proposal', sourceSegmentIds: const ['seg-1']);
      final session = sessionWith(
        newIdempotencyKey: () => 'stable-key',
        onCreate: (item, completed, idempotencyKey) async => 'task-1',
        onUpdate: (_, __) async => true,
        onItemUpdate: (_, __) async => true,
      );
      await session.setCompleted(twin, 0, true, row: 0);
      expect(session.taskIdFor(twin, row: 0), 'task-1');
      expect(session.taskIdFor(twin, row: 1), isNull, reason: 'the sibling row has no task yet');
    });

    test('check-off failures do not mark the summary item complete', () async {
      final session = sessionWith(
        newIdempotencyKey: () => 'stable-key',
        onCreate: (item, completed, idempotencyKey) async => null,
        onUpdate: (_, __) async => true,
        onItemUpdate: (index, completed) async {
          fail('summary must not update when the task create failed');
        },
      );
      final item = ActionItem('Send the proposal', sourceSegmentIds: const ['segment-1']);

      expect(await session.setCompleted(item, 0, true), isNull);
    });

    test('a conversation PATCH failure rolls back the task it just created', () async {
      // The create succeeded but the note never absorbed it: the task minted by
      // this call is deleted and its link forgotten, so no orphan completes
      // silently and a retry mints a fresh task.
      final deleted = <String>[];
      final stored = <String, String>{};
      final session = sessionWith(
        newIdempotencyKey: () => 'stable-key',
        onCreate: (item, completed, idempotencyKey) async => 'task-1',
        onUpdate: (_, __) async => true,
        onItemUpdate: (_, __) async => false,
        onDelete: (id) async {
          deleted.add(id);
          return true;
        },
        readPersistedTaskIds: () async => Map.of(stored),
        writePersistedTaskIds: (taskIds) async => stored
          ..clear()
          ..addAll(taskIds),
      );
      final item = ActionItem('Send the proposal', sourceSegmentIds: const ['segment-1']);

      expect(await session.setCompleted(item, 0, true), isNull);
      expect(deleted, ['task-1']);
      expect(stored, isEmpty);
      expect(session.taskIdFor(item), isNull);
    });

    test('a conversation PATCH failure restores the task it toggled', () async {
      // The linked task was completed but the note stayed open: the previous
      // state is restored so Tasks and the summary cannot disagree.
      final updates = <(String, bool)>[];
      final session = sessionWith(
        newIdempotencyKey: () => 'stable-key',
        onCreate: (item, completed, idempotencyKey) async => 'task-1',
        onUpdate: (id, completed) async {
          updates.add((id, completed));
          return true;
        },
        onItemUpdate: (_, __) async => false,
      );
      final item = ActionItem('Send the proposal', sourceSegmentIds: const ['segment-1'], targetTaskId: 'task-1');

      expect(await session.setCompleted(item, 0, true), isNull);
      expect(updates, [('task-1', true), ('task-1', false)]);
    });

    test('a reprocessed note resolves the row before patching, or refuses', () async {
      // The captured index went stale after reprocessing: the write targets the
      // row's current position, and a vanished or ambiguous row patches nothing.
      final patched = <int>[];
      final session = sessionWith(
        newIdempotencyKey: () => 'stable-key',
        onCreate: (item, completed, idempotencyKey) async => 'task-1',
        onUpdate: (_, __) async => true,
        onItemUpdate: (index, completed) async {
          patched.add(index);
          return true;
        },
      );
      final item = ActionItem('Send the proposal', sourceSegmentIds: const ['segment-1'], targetTaskId: 'task-1');

      // A new row was inserted above ours: index 0 now belongs to another item.
      final reprocessed = [
        ActionItem('A new commitment'),
        ActionItem('Send the proposal', sourceSegmentIds: const ['segment-1'], targetTaskId: 'task-1'),
      ];
      expect(await session.setCompleted(item, 0, true, row: 0, currentRows: reprocessed), 1);
      expect(patched, [1]);

      // The row is gone entirely: nothing is patched.
      expect(await session.setCompleted(item, 1, false, row: 1, currentRows: [ActionItem('A new commitment')]), isNull);
      expect(patched, [1]);
    });
  });
}
