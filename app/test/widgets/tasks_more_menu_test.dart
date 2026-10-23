import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/tasks_more_menu.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/ui/ui.dart';

// Tasks' page actions live in one bare "⋯" beside the Home / Tasks switcher: the completed view
// and task integrations, with no circle behind the glyph.
void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<ActionItemsProvider> pump(WidgetTester tester) async {
    final provider = ActionItemsProvider(
      getActionItems: (
              {limit = 50,
              offset = 0,
              completed,
              conversationId,
              startDate,
              endDate,
              dueStartDate,
              dueEndDate}) async =>
          const ActionItemsResponse(actionItems: [], hasMore: false),
    );
    addTearDown(provider.dispose);
    await tester.pumpWidget(
      ChangeNotifierProvider<ActionItemsProvider>.value(
        value: provider,
        child: const MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: Center(child: TasksMoreMenu())),
        ),
      ),
    );
    return provider;
  }

  testWidgets('the button is a bare glyph with a spoken label', (tester) async {
    await pump(tester);
    final button = tester.widget<OmiIconButton>(find.byKey(TasksMoreMenu.buttonKey));
    expect(button.filled, isFalse);
    expect(find.bySemanticsLabel('More options'), findsOneWidget);
  });

  testWidgets('the menu holds the completed view and task integrations, even with no tasks', (tester) async {
    final provider = await pump(tester);
    await tester.tap(find.byKey(TasksMoreMenu.buttonKey));
    await tester.pumpAndSettle();
    expect(find.text('Show Completed'), findsOneWidget);
    expect(find.text("Task Integrations"), findsOneWidget);

    await tester.tap(find.text('Show Completed'));
    await tester.pumpAndSettle();
    expect(provider.showCompletedView, isTrue);
  });
}
