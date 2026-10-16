import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/review/recent_changes_page.dart';
import 'package:omi/ui/ui.dart';

// Invented content only.
ReviewChange _term(String id, String conversation, {int places = 1, bool undone = false, int day = 14}) => ReviewChange(
      changeId: id,
      kind: ReviewChangeKind.other,
      editKind: 'transcript',
      title: 'Edit transcript',
      reason: 'Matches your contact',
      before: 'whole segment that must not be shown',
      after: 'whole corrected segment',
      createdAt: DateTime.utc(2026, 10, day, 12),
      groupKey: 'term:zentrix',
      refs: [ReviewChangeRef(type: 'conversation', id: 'conv-$id', label: conversation)],
      diff: ReviewChangeDiff(
        before: 'zen tricks',
        after: 'Zentrix',
        occurrenceCount: places,
        sourceTitle: conversation,
        occurrences: const [
          ReviewChangeOccurrence(
              contextBefore: 'Ask ', before: 'zen tricks', after: 'Zentrix', contextAfter: ' today.'),
        ],
      ),
      undone: undone,
    );

final _memory = ReviewChange(
  changeId: 'memory-1',
  kind: ReviewChangeKind.other,
  editKind: 'supersede_memory',
  title: 'Supersede memory',
  reason: 'Supersede memory',
  before: 'Prefers tea in the morning',
  after: 'Prefers coffee in the morning since moving',
  createdAt: DateTime.utc(2026, 10, 13, 9),
  refs: const [ReviewChangeRef(type: 'memory', id: 'mem-1', label: 'Prefers tea in the morning')],
  diff: ReviewChangeDiff(
    before: 'Prefers tea in the morning',
    after: 'Prefers coffee in the morning since moving',
    sourceTitle: 'Synthetic breakfast chat',
    sourceStartedAt: DateTime.utc(2026, 10, 12, 8),
  ),
);

final _task = ReviewChange(
  changeId: 'task-1',
  kind: ReviewChangeKind.other,
  editKind: 'merge_tasks',
  title: 'Merge tasks',
  before: 'Email the invented vendor\nSend vendor the invented contract',
  after: 'Send the invented vendor the contract',
  createdAt: DateTime.utc(2026, 10, 13, 10),
);

const _uuid = '3f2b8c1e-5d4a-4f6b-9c2e-1a7d8e9f0b3c';

final _legacy = ReviewChange(
  changeId: 'legacy-1',
  kind: ReviewChangeKind.closeTask,
  title: 'Closed an invented task',
  reason: 'Closed an invented task',
  createdAt: DateTime.utc(2026, 10, 10, 10),
  refs: const [ReviewChangeRef(type: 'conversation', id: _uuid, label: _uuid)],
);

Future<void> _pump(
  WidgetTester tester,
  List<ReviewChange> changes, {
  ReviewChangeToggler? setUndone,
  void Function(BuildContext, String)? openConversation,
  void Function(BuildContext)? openTasks,
}) async {
  tester.view.physicalSize = const Size(900, 2400);
  tester.view.devicePixelRatio = 2;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  OmiColors.active = OmiColors.forBrightness(Brightness.dark);
  await tester.pumpWidget(MaterialApp(
    theme: buildOmiTheme(brightness: Brightness.dark),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: RecentChangesPage(
      loadChanges: ({cursor}) async => ApiSuccess(ReviewChangesPage(changes: changes)),
      setUndone: setUndone ??
          (id, {required undone}) async =>
              ApiSuccess(changes.firstWhere((c) => c.changeId == id).copyWith(undone: undone)),
      openConversation: openConversation ?? (_, __) {},
      openTasks: openTasks ?? (_) {},
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('one term respelled across conversations is one row with counts and Undo all', (tester) async {
    await _pump(tester, [
      _term('t1', 'Synthetic pilot sync', places: 3, day: 14),
      _term('t2', 'Synthetic budget call', places: 4, day: 12),
    ]);
    expect(find.text('NAMES AND TERMS'), findsOneWidget);
    expect(find.text('zen tricks'), findsOneWidget);
    expect(find.text('Zentrix'), findsOneWidget);
    expect(find.text('2 conversations · 7 places'), findsOneWidget);
    expect(find.text('Show all 7'), findsOneWidget);
    expect(find.text('Undo all'), findsOneWidget);
    expect(find.text('Matches your contact'), findsOneWidget);
    // The span diff replaces the whole stored segments, and the title never repeats.
    expect(find.text('whole segment that must not be shown'), findsNothing);
    expect(find.text('Edit transcript'), findsNothing);
  });

  testWidgets('memory, task and legacy rows render before → after without ids or repeated reasons', (tester) async {
    await _pump(tester, [_memory, _task, _legacy]);
    expect(find.text('MEMORIES'), findsOneWidget);
    expect(find.text('Prefers tea in the morning'), findsOneWidget);
    expect(find.text('Prefers coffee in the morning since moving'), findsOneWidget);
    expect(find.textContaining('Synthetic breakfast chat'), findsOneWidget);
    expect(find.text('Supersede memory'), findsNothing);
    expect(find.text('See evidence'), findsWidgets);

    expect(find.text('TASKS'), findsOneWidget);
    expect(find.text('Email the invented vendor'), findsOneWidget);
    expect(find.text('Send vendor the invented contract'), findsOneWidget);
    expect(find.text('Send the invented vendor the contract'), findsOneWidget);
    expect(find.text('View task'), findsWidgets);

    // A legacy row with nothing to compare keeps its title once, never the UUID.
    expect(find.text('Closed an invented task'), findsOneWidget);
    expect(find.textContaining(_uuid), findsNothing);
  });

  testWidgets('Show all opens each place in context with per-conversation Undo and View conversation', (tester) async {
    final opened = <String>[];
    final toggled = <String>[];
    final changes = [_term('t1', 'Synthetic pilot sync', places: 3), _term('t2', 'Synthetic budget call', day: 12)];
    await _pump(
      tester,
      changes,
      openConversation: (_, id) => opened.add(id),
      setUndone: (id, {required undone}) async {
        toggled.add(id);
        return ApiSuccess(changes.firstWhere((c) => c.changeId == id).copyWith(undone: undone));
      },
    );
    await tester.tap(find.text('Show all 4'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('recent_change_sheet')), findsOneWidget);
    expect(find.byKey(const Key('recent_change_occurrence')), findsNWidgets(2));
    expect(find.textContaining('Synthetic pilot sync ·'), findsOneWidget);
    expect(find.textContaining('Synthetic budget call ·'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('recent_change_open_conversation_t2')));
    await tester.pumpAndSettle();
    expect(opened, ['conv-t2']);

    await tester.tap(find.byKey(const ValueKey('review_change_toggle_t2')));
    await tester.pumpAndSettle();
    expect(toggled, ['t2']);
    // The sheet follows the new state, and the page row now has one change left to undo.
    expect(find.descendant(of: find.byKey(const ValueKey('review_change_toggle_t2')), matching: find.text('Redo')),
        findsOneWidget);
    expect(find.descendant(of: find.byKey(const ValueKey('recent_change_toggle_t1')), matching: find.text('Undo')),
        findsOneWidget);
  });

  testWidgets('Undo all runs each undo in turn and reports partial failure', (tester) async {
    final changes = [
      _term('t1', 'Synthetic pilot sync', day: 14),
      _term('t2', 'Synthetic budget call', day: 13),
      _term('t3', 'Synthetic standup', day: 12),
    ];
    final calls = <String>[];
    await _pump(tester, changes, setUndone: (id, {required undone}) async {
      calls.add(id);
      if (id == 't2') return const ApiFailure(ApiProblem(ApiProblemKind.transport));
      return ApiSuccess(changes.firstWhere((c) => c.changeId == id).copyWith(undone: undone));
    });
    await tester.tap(find.text('Undo all'));
    await tester.pumpAndSettle();
    expect(calls, ['t1', 't2', 't3']);
    expect(find.text('Couldn’t undo 1 of 3. Try again.'), findsOneWidget);
    // One change is still applied, so the row offers a single Undo rather than Redo.
    expect(find.descendant(of: find.byKey(const ValueKey('recent_change_toggle_t1')), matching: find.text('Undo')),
        findsOneWidget);
  });
}
