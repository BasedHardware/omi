import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';

ActionItemWithMetadata _item(String id) => ActionItemWithMetadata(id: id, description: id, completed: false);

Future<ActionItemsResponse?> _empty({
  int limit = 100,
  int offset = 0,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
  DateTime? dueStartDate,
  DateTime? dueEndDate,
}) async =>
    const ActionItemsResponse(actionItems: []);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<ActionItemsProvider> provider(DeleteActionItemRequest deleter) async {
    final p = ActionItemsProvider(getActionItems: _empty, deleteActionItemRequest: deleter);
    await p.ensureLoaded();
    addTearDown(p.dispose);
    p.actionItems.addAll([_item('a'), _item('b'), _item('c')]);
    return p;
  }

  test('a rejected delete puts the task back where it was', () async {
    final p = await provider((_) async => false);

    final ok = await p.deleteActionItem(p.actionItems[1]);

    expect(ok, isFalse);
    expect(p.actionItems.map((i) => i.id), ['a', 'b', 'c']);
  });

  test('a delete that throws puts the task back where it was', () async {
    final p = await provider((_) async => throw Exception('offline'));

    final ok = await p.deleteActionItem(p.actionItems[1]);

    expect(ok, isFalse);
    expect(p.actionItems.map((i) => i.id), ['a', 'b', 'c']);
  });

  test('a confirmed delete keeps the task removed', () async {
    final p = await provider((_) async => true);

    final ok = await p.deleteActionItem(p.actionItems[1]);

    expect(ok, isTrue);
    expect(p.actionItems.map((i) => i.id), ['a', 'c']);
  });
}
