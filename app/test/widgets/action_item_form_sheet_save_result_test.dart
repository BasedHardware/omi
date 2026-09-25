import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/providers/action_items_provider.dart';

Future<ActionItemsResponse?> _noItems({
  int limit = 50,
  int offset = 0,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
  DateTime? dueStartDate,
  DateTime? dueEndDate,
}) async =>
    const ActionItemsResponse(actionItems: [], hasMore: false);

Future<void> _editDescription(WidgetTester tester, ActionItemsProvider provider) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<ActionItemsProvider>.value(
      value: provider,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                // The sheet pops itself before saving, so it has to be a real route.
                onPressed: () => showModalBottomSheet<void>(
                  context: context,
                  builder: (_) => const ActionItemFormSheet(
                    actionItem: ActionItemWithMetadata(id: 'task-1', description: 'Buy milk', completed: false),
                  ),
                ),
                child: const Text('open sheet'),
              ),
            ),
          ),
        ),
      ),
    ),
  );

  await tester.tap(find.text('open sheet'));
  await tester.pumpAndSettle();

  await tester.enterText(find.byType(TextField).first, 'Buy oat milk');
  await tester.testTextInput.receiveAction(TextInputAction.done);
  await tester.pumpAndSettle();
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('a rejected edit is not reported as saved', (tester) async {
    final provider = ActionItemsProvider(
      getActionItems: _noItems,
      updateActionItemRequest: (id, {description, completed, dueAt}) async => null,
    );
    addTearDown(provider.dispose);

    await _editDescription(tester, provider);

    expect(find.text('Task updated'), findsNothing);
    expect(find.text('Failed to update task'), findsOneWidget);
  });

  testWidgets('an accepted edit is reported as saved', (tester) async {
    final provider = ActionItemsProvider(
      getActionItems: _noItems,
      updateActionItemRequest: (id, {description, completed, dueAt}) async =>
          ActionItemWithMetadata(id: id, description: description ?? 'Buy milk', completed: false),
    );
    addTearDown(provider.dispose);

    await _editDescription(tester, provider);

    expect(find.text('Task updated'), findsOneWidget);
    expect(find.text('Failed to update task'), findsNothing);
  });
}
