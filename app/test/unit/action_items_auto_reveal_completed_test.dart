import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;
import 'package:omi/providers/action_items_provider.dart';

ActionItemWithMetadata _item({required bool completed, String id = 'task'}) {
  return wire.GeneratedActionItemResponse(
    id: id,
    description: 'Do the thing',
    completed: completed,
  );
}

void main() {
  group('ActionItemsProvider.shouldAutoRevealCompleted', () {
    test('reveals completed view when every task is completed', () {
      final items = [
        _item(completed: true, id: 'a'),
        _item(completed: true, id: 'b'),
      ];
      expect(ActionItemsProvider.shouldAutoRevealCompleted(items), isTrue);
    });

    test('keeps active view when at least one task is incomplete', () {
      final items = [
        _item(completed: true, id: 'a'),
        _item(completed: false, id: 'b'),
      ];
      expect(ActionItemsProvider.shouldAutoRevealCompleted(items), isFalse);
    });

    test('keeps active view when all tasks are incomplete', () {
      final items = [_item(completed: false, id: 'a')];
      expect(ActionItemsProvider.shouldAutoRevealCompleted(items), isFalse);
    });

    test('does not reveal for a genuine empty list', () {
      expect(ActionItemsProvider.shouldAutoRevealCompleted(const []), isFalse);
    });
  });
}
