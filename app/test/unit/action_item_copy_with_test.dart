import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;

wire.GeneratedActionItemResponse _sampleItem({String? goalId, String? workstreamId}) {
  final now = DateTime.utc(2026, 1, 1);
  return wire.GeneratedActionItemResponse(
    id: 'task_1',
    description: 'Follow up',
    completed: false,
    createdAt: now,
    updatedAt: now,
    goalId: goalId,
    workstreamId: workstreamId,
  );
}

void main() {
  test('copyWith preserves goalId and workstreamId when omitted', () {
    final item = _sampleItem(goalId: 'goal_1', workstreamId: 'ws_1');
    final updated = item.copyWith(description: 'Updated');

    expect(updated.goalId, 'goal_1');
    expect(updated.workstreamId, 'ws_1');
  });

  test('copyWith allows explicitly clearing goalId and workstreamId', () {
    final item = _sampleItem(goalId: 'goal_1', workstreamId: 'ws_1');
    final updated = item.copyWith(goalId: null, workstreamId: null);

    expect(updated.goalId, isNull);
    expect(updated.workstreamId, isNull);
  });
}
