import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/goals.dart';

void main() {
  test('Goal.fromJson backfills required canonical fields for sparse legacy payloads', () {
    final goal = Goal.fromJson({
      'id': 'goal_legacy',
      'title': 'Read more',
      'is_active': true,
      'created_at': '2026-01-01T00:00:00Z',
    });

    expect(goal.id, 'goal_legacy');
    expect(goal.title, 'Read more');
    expect(goal.goalType, 'scale');
    expect(goal.targetValue, 0);
    expect(goal.maxValue, 10);
    expect(goal.isActive, isTrue);
  });

  test('Goal.fromJson parses qualitative goals with metric null', () {
    final goal = Goal.fromJson({
      'id': 'goal_qualitative',
      'goal_id': 'goal_qualitative',
      'title': 'Launch desktop',
      'desired_outcome': 'Ship a trustworthy release',
      'status': 'background',
      'source': 'user',
      'metric': null,
      'target_value': 0,
      'current_value': 0,
      'min_value': 0,
      'max_value': 0,
      'goal_type': 'scale',
      'is_active': true,
      'created_at': '2026-01-01T00:00:00Z',
      'updated_at': '2026-01-01T00:00:00Z',
    });

    expect(goal.id, 'goal_qualitative');
    expect(goal.targetValue, 0);
    expect(goal.maxValue, 0);
  });
}
