import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/prompts/prompt_queue.dart';

/// Startup prompts: one at a time, highest priority first, no duplicates, nothing while busy.
void main() {
  late GlobalKey<NavigatorState> navigatorKey;
  late PromptQueue queue;
  late List<String> shown;

  Future<void> pumpApp(WidgetTester tester) async {
    navigatorKey = GlobalKey<NavigatorState>();
    queue = PromptQueue(contextProvider: () => navigatorKey.currentState?.overlay?.context);
    shown = [];
    await tester.pumpWidget(MaterialApp(navigatorKey: navigatorKey, home: const Scaffold(body: SizedBox())));
  }

  PromptPresenter dialog(String id) => (context) {
        shown.add(id);
        return showDialog<void>(
          context: context,
          builder: (c) => AlertDialog(
            title: Text(id),
            actions: [TextButton(onPressed: () => Navigator.pop(c), child: Text('close $id'))],
          ),
        );
      };

  Future<void> closeCurrent(WidgetTester tester) async {
    await tester.tap(find.textContaining('close '));
    await tester.pumpAndSettle();
  }

  testWidgets('shows one prompt at a time in priority order, then arrival order', (tester) async {
    await pumpApp(tester);
    queue.enqueue('review', PromptPriority.low, show: dialog('review'));
    queue.enqueue('changelog', PromptPriority.normal, show: dialog('changelog'));
    queue.enqueue('firmware', PromptPriority.high, show: dialog('firmware'));
    queue.enqueue('announcement', PromptPriority.normal, show: dialog('announcement'));
    await tester.pumpAndSettle();

    // Everything was queued in the same frame; the highest priority wins the first slot.
    expect(shown, ['firmware']);
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(queue.pendingIds, ['changelog', 'announcement', 'review']);

    await closeCurrent(tester);
    expect(shown, ['firmware', 'changelog']);
    await closeCurrent(tester);
    await closeCurrent(tester);
    await closeCurrent(tester);
    expect(shown, ['firmware', 'changelog', 'announcement', 'review']);
    expect(queue.showingId, isNull);
  });

  testWidgets('dedupes by id while queued or showing', (tester) async {
    await pumpApp(tester);
    expect(queue.enqueue('upgrade', PromptPriority.critical, show: dialog('upgrade')), isTrue);
    expect(queue.enqueue('upgrade', PromptPriority.critical, show: dialog('upgrade')), isFalse);
    await tester.pumpAndSettle();
    expect(queue.showingId, 'upgrade');
    expect(queue.enqueue('upgrade', PromptPriority.critical, show: dialog('upgrade')), isFalse);
    await closeCurrent(tester);
    expect(shown, ['upgrade']);
    // Once it has closed, the same id may be queued again (e.g. next launch).
    expect(queue.enqueue('upgrade', PromptPriority.critical, show: dialog('upgrade')), isTrue);
  });

  testWidgets('holds everything while blocked, resumes on pump', (tester) async {
    await pumpApp(tester);
    var recording = true;
    queue.blocked = () => recording;
    queue.enqueue('changelog', PromptPriority.normal, show: dialog('changelog'));
    await tester.pumpAndSettle();
    expect(shown, isEmpty);

    recording = false;
    queue.pump();
    await tester.pumpAndSettle();
    expect(shown, ['changelog']);
  });

  testWidgets('a prompt waits for its own condition without blocking the others', (tester) async {
    await pumpApp(tester);
    var connected = false;
    queue.enqueue('tutorial', PromptPriority.high, show: dialog('tutorial'), canShowNow: () => connected);
    queue.enqueue('changelog', PromptPriority.normal, show: dialog('changelog'));
    await tester.pumpAndSettle();
    expect(shown, ['changelog']);
    await closeCurrent(tester);
    expect(shown, ['changelog']);

    connected = true;
    queue.pump();
    await tester.pumpAndSettle();
    expect(shown, ['changelog', 'tutorial']);
  });

  testWidgets('a presenter that throws does not wedge the queue', (tester) async {
    await pumpApp(tester);
    final errors = <FlutterErrorDetails>[];
    final previous = FlutterError.onError;
    FlutterError.onError = errors.add;
    addTearDown(() => FlutterError.onError = previous);

    queue.enqueue('broken', PromptPriority.high, show: (_) async => throw StateError('boom'));
    queue.enqueue('next', PromptPriority.normal, show: dialog('next'));
    await tester.pumpAndSettle();
    expect(errors, hasLength(1));
    expect(shown, ['next']);
  });

  testWidgets('remove drops a queued prompt', (tester) async {
    await pumpApp(tester);
    queue.blocked = () => true;
    queue.enqueue('a', PromptPriority.normal, show: dialog('a'));
    expect(queue.remove('a'), isTrue);
    queue.blocked = () => false;
    queue.pump();
    await tester.pumpAndSettle();
    expect(shown, isEmpty);
  });
}
