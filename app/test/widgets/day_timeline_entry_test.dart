import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/task_completion_circle.dart';
import 'package:omi/pages/home/widgets/day_timeline_entry.dart';

void main() {
  testWidgets('shows the conversation with the tasks it produced', (tester) async {
    final now = DateTime.now();
    ActionItemWithMetadata? toggled;

    await _pumpEntry(
      tester,
      conversation: _conversation(
        id: 'a',
        title: 'Design crit on the home screen',
        startedAt: DateTime(now.year, now.month, now.day, 11, 45),
        durationSeconds: 29 * 60,
      ),
      tasks: [
        _task(id: 't1', description: 'Share crit notes', dueAt: DateTime(now.year, now.month, now.day - 2)),
        _task(id: 't2', description: 'Cut the mind map'),
      ],
      onToggleTask: (task) => toggled = task,
    );

    expect(find.text('Design crit on the home screen'), findsOneWidget);
    expect(find.text('29m'), findsOneWidget);
    // The rows already run through the day, so the meridiem is dropped.
    expect(find.text('11:45'), findsOneWidget);
    expect(find.textContaining('AM'), findsNothing);
    expect(find.textContaining('PM'), findsNothing);
    expect(find.text('Share crit notes'), findsOneWidget);
    expect(find.text('Cut the mind map'), findsOneWidget);
    // Past due and still open reads as overdue; a task with no due date has no marker.
    expect(find.text('Overdue'), findsOneWidget);

    await tester.tap(find.text('Share crit notes'), warnIfMissed: false);
    expect(toggled, isNull, reason: 'only the completion circle toggles a task');

    await tester.tap(find.byType(TaskCompletionCircle).first);
    expect(toggled?.id, 't1');
  });

  testWidgets('opens the conversation when its row is tapped', (tester) async {
    var opened = 0;

    await _pumpEntry(
      tester,
      conversation: _conversation(id: 'a', title: 'Standup', startedAt: DateTime(2026, 7, 15, 9), durationSeconds: 660),
      tasks: const [],
      onTap: () => opened++,
    );

    await tester.tap(find.text('Standup'));
    expect(opened, 1);
  });

  test('formats a conversation duration the way the timeline reads it', () {
    expect(formatConversationDuration(0), '0s');
    expect(formatConversationDuration(42), '42s');
    expect(formatConversationDuration(60), '1m');
    expect(formatConversationDuration(29 * 60 + 30), '29m');
    expect(formatConversationDuration(3600), '1h');
    expect(formatConversationDuration(3600 + 5 * 60), '1h 5m');
  });
}

Future<void> _pumpEntry(
  WidgetTester tester, {
  required ServerConversation conversation,
  required List<ActionItemWithMetadata> tasks,
  VoidCallback? onTap,
  void Function(ActionItemWithMetadata task)? onToggleTask,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        backgroundColor: Colors.black,
        body: DayTimelineEntry(
          conversation: conversation,
          tasks: tasks,
          onTap: onTap ?? () {},
          onToggleTask: onToggleTask ?? (_) {},
        ),
      ),
    ),
  );
  await tester.pump();
}

ServerConversation _conversation({
  required String id,
  required String title,
  required DateTime startedAt,
  int durationSeconds = 0,
}) {
  return ServerConversation(
    id: id,
    createdAt: startedAt,
    startedAt: startedAt,
    structured: Structured(title, 'Overview', emoji: '🧠'),
    transcriptSegments: [
      TranscriptSegment(
        id: '$id-0',
        text: 'hello',
        speaker: 'SPEAKER_0',
        isUser: false,
        personId: null,
        start: 0,
        end: durationSeconds.toDouble(),
        translations: const [],
      ),
    ],
  );
}

ActionItemWithMetadata _task({
  required String id,
  required String description,
  DateTime? dueAt,
  bool completed = false,
}) {
  return ActionItemWithMetadata(id: id, description: description, completed: completed, dueAt: dueAt);
}
