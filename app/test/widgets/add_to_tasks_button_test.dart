// Guards the "Add to Tasks" state machine, not the network.
//
// Capture is suggestion-only (INV-TASK-2), so this button is the mobile gesture
// that turns an extracted action item into a task. The states it must honour:
// a second tap while a create is in flight is a no-op, an added item stops
// offering the gesture, and a failure returns to idle so the user can retry.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/add_to_tasks_button.dart';

Widget _host(Widget child) => MaterialApp(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

void main() {
  const button = AddToTasksButton(description: 'Buy milk', conversationId: 'conv-1');

  testWidgets('offers the gesture while idle', (tester) async {
    await tester.pumpWidget(_host(button));
    await tester.pump();

    final state = tester.state<AddToTasksButtonState>(find.byType(AddToTasksButton));
    expect(state.state, AddToTasksState.idle);
    expect(find.byIcon(Icons.playlist_add), findsOneWidget);
  });

  testWidgets('an added item confirms and stops offering the gesture', (tester) async {
    await tester.pumpWidget(_host(button));
    await tester.pump();

    tester.state<AddToTasksButtonState>(find.byType(AddToTasksButton)).setStateForTesting(AddToTasksState.added);
    await tester.pump();

    expect(find.byIcon(Icons.check), findsOneWidget);
    expect(find.byIcon(Icons.playlist_add), findsNothing);
  });

  testWidgets('a create in flight shows progress and refuses a second tap', (tester) async {
    await tester.pumpWidget(_host(button));
    await tester.pump();

    final state = tester.state<AddToTasksButtonState>(find.byType(AddToTasksButton));
    state.setStateForTesting(AddToTasksState.adding);
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.byIcon(Icons.playlist_add), findsNothing);

    // add() is a no-op unless idle, so an in-flight create cannot be duplicated.
    await state.add();
    expect(state.state, AddToTasksState.adding);
  });
}
