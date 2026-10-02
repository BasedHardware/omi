import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/schema.dart';
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('toggling completion does not write back the description and due date of the copy it was given', () async {
    final server = <String, Object?>{
      'description': 'Buy oat milk',
      'completed': true,
      'due_at': DateTime.utc(2026, 9, 26),
    };
    final provider = ActionItemsProvider(
      getActionItems: _noItems,
      updateActionItemRequest: (id, {description, completed, dueAt}) async {
        if (description != null) server['description'] = description;
        if (completed != null) server['completed'] = completed;
        if (dueAt != null) server['due_at'] = dueAt;
        return ActionItemWithMetadata(id: id, description: server['description'] as String, completed: false);
      },
    );
    addTearDown(provider.dispose);

    final staleCopy = ActionItemWithMetadata(
      id: 'task-1',
      description: 'Buy milk',
      completed: true,
      dueAt: DateTime.utc(2026, 9, 20),
    );
    await provider.updateActionItemState(staleCopy, false);

    expect(server, {'description': 'Buy oat milk', 'completed': false, 'due_at': DateTime.utc(2026, 9, 26)});
  });
}
