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

ActionItemWithMetadata _item() =>
    const ActionItemWithMetadata(id: 'task-1', description: 'Buy milk', completed: false);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('a rejected write is reported to the caller', () async {
    final provider = ActionItemsProvider(
      getActionItems: _noItems,
      updateActionItemRequest: (id, {description, completed, dueAt}) async => null,
    );
    addTearDown(provider.dispose);

    expect(await provider.updateActionItemState(_item(), true), isFalse);
    expect(await provider.updateActionItemDescription(_item(), 'Buy oat milk'), isFalse);
  });

  test('an accepted write is reported to the caller', () async {
    final provider = ActionItemsProvider(
      getActionItems: _noItems,
      updateActionItemRequest: (id, {description, completed, dueAt}) async =>
          ActionItemWithMetadata(id: id, description: description ?? 'Buy milk', completed: completed ?? false),
    );
    addTearDown(provider.dispose);

    expect(await provider.updateActionItemState(_item(), true), isTrue);
    expect(await provider.updateActionItemDescription(_item(), 'Buy oat milk'), isTrue);
  });
}
