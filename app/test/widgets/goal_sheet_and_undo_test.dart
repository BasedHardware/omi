import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/goal_form_sheet.dart';
import 'package:omi/providers/goals_provider.dart';

Goal _goal(String id, String title) => Goal(
      id: id,
      title: title,
      goalType: 'numeric',
      targetValue: 10,
      currentValue: 3,
      minValue: 0,
      maxValue: 10,
      isActive: true,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
    );

Widget _app(Widget Function(BuildContext) body) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(body: Builder(builder: body)),
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'goal-user'});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a staged goal delete hides it and Undo restores it in place', (tester) async {
    final provider =
        GoalsProvider(goalsFetcher: () async => [_goal('a', 'Read'), _goal('b', 'Run'), _goal('c', 'Save')]);
    addTearDown(provider.dispose);
    await provider.loadGoals();
    await tester.pump();

    await tester.pumpWidget(_app((context) => TextButton(
          onPressed: () => deleteGoalWithUndo(context, provider, provider.goals[1]),
          child: const Text('delete'),
        )));
    await tester.tap(find.text('delete'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byType(AlertDialog), findsNothing, reason: 'goal deletes are Undo-only (D5)');
    expect(provider.goals.map((g) => g.id), ['a', 'c']);
    expect(provider.isGoalDeleteStaged('b'), isTrue);
    expect(find.text('Goal deleted'), findsOneWidget);

    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(provider.goals.map((g) => g.id), ['a', 'b', 'c']);
    expect(provider.isGoalDeleteStaged('b'), isFalse);
  });

  testWidgets('the goal sheet asks before discarding an edited title', (tester) async {
    String? saved;
    await tester.pumpWidget(_app((context) => TextButton(
          onPressed: () => showGoalFormSheet(
            context,
            goal: _goal('a', 'Read books'),
            onSave: (title, current, target, emoji) => saved = title,
          ),
          child: const Text('open'),
        )));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('Edit Goal'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, 'Read books'), 'Read 12 books');
    await tester.pump();
    await tester.tap(find.byTooltip('Close'));
    await tester.pumpAndSettle();
    expect(find.text('Discard Changes?'), findsOneWidget);
    await tester.tap(find.text('Keep Editing'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('goal_save_button')));
    await tester.pumpAndSettle();
    expect(saved, 'Read 12 books');
    expect(find.text('Edit Goal'), findsNothing);
  });
}
