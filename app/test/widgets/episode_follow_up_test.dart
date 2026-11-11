import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/episodes/episode_follow_up.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/episode_tasks_fixture.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<void> pump(WidgetTester tester, ActionItemsProvider tasks,
      {String episode = 'episode-1', String text = 'Check seed trays', String? conversation = 'conversation-1'}) async {
    await tester.pumpWidget(ChangeNotifierProvider<ActionItemsProvider>.value(
      value: tasks,
      child: MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(body: EpisodeFollowUp(episodeId: episode, text: text, conversationId: conversation)),
      ),
    ));
    await tester.pump();
  }

  testWidgets('double tap creates exactly one linked todo; saved button is disabled', (tester) async {
    final response = Completer<ActionItemWithMetadata?>();
    var calls = 0;
    String? source;
    String? key;
    final tasks =
        episodeTasks(create: ({required description, dueAt, conversationId, completed = false, idempotencyKey}) {
      calls++;
      expect(description, 'Check seed trays');
      expect(completed, isFalse);
      source = conversationId;
      key = idempotencyKey;
      return response.future;
    });
    addTearDown(tasks.dispose);
    await pump(tester, tasks);
    final add = find.byType(OmiIconButton);
    await tester.tap(add);
    await tester.tap(add); // Before rebuilding: the synchronous in-flight guard also applies.
    expect(calls, 1);
    expect(source, 'conversation-1');
    expect(key, startsWith('episode-follow-up:'));
    await tester.pump();
    expect(tester.widget<OmiIconButton>(add).onPressed, isNull);
    response.complete(ActionItemWithMetadata(
        id: 'task-1', description: 'Check seed trays', completed: false, conversationId: source));
    await tester.pumpAndSettle();
    expect(tasks.actionItems, hasLength(1));
    expect(tasks.actionItems.single.id, 'task-1');
    expect(tasks.actionItems.single.conversationId, 'conversation-1');
    expect(find.byTooltip('Added to Tasks'), findsOneWidget);
    await tester.tap(add);
    expect(calls, 1);
  });

  testWidgets('lost response and page reopen reuse the same server idempotency key', (tester) async {
    final keys = <String>[];
    final server = <String, ActionItemWithMetadata>{};
    final tasks =
        episodeTasks(create: ({required description, dueAt, conversationId, completed = false, idempotencyKey}) async {
      keys.add(idempotencyKey!);
      final task = server.putIfAbsent(
          idempotencyKey,
          () => ActionItemWithMetadata(
              id: 'task-1', description: description, completed: false, conversationId: conversationId));
      return keys.length == 1 ? null : task; // Server accepted it; first response was lost.
    });
    addTearDown(tasks.dispose);
    await pump(tester, tasks);
    await tester.tap(find.byType(OmiIconButton));
    await tester.pump();
    expect(tester.widget<OmiIconButton>(find.byType(OmiIconButton)).onPressed, isNotNull);
    await tester.tap(find.byType(OmiIconButton));
    await tester.pump();
    await tester.pumpWidget(const SizedBox.shrink());
    await pump(tester, tasks);
    await tester.tap(find.byType(OmiIconButton));
    await tester.pump();
    expect(keys, hasLength(3));
    expect(keys.toSet(), hasLength(1));
    expect(server, hasLength(1));
    expect(tasks.actionItems, hasLength(1));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('missing retained source cannot create an unlinked task', (tester) async {
    var calls = 0;
    final tasks =
        episodeTasks(create: ({required description, dueAt, conversationId, completed = false, idempotencyKey}) async {
      calls++;
      return null;
    });
    addTearDown(tasks.dispose);
    await pump(tester, tasks, conversation: null);
    expect(tester.widget<OmiIconButton>(find.byType(OmiIconButton)).onPressed, isNull);
    await tester.tap(find.byType(OmiIconButton));
    expect(calls, 0);
  });
}
