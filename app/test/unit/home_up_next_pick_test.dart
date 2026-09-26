import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/home/widgets/home_sections.dart';

ActionItemWithMetadata _task(String id, {DateTime? dueAt}) =>
    ActionItemWithMetadata(id: id, description: id, completed: false, dueAt: dueAt);

/// Home's Up next shows what is coming ahead of its day, not only today's tasks (#5080).
void main() {
  test("today's tasks lead, then the rest soonest due first, undated last", () {
    final today = [_task('call')];
    final open = [
      _task('undated'),
      _task('friday', dueAt: DateTime(2026, 10, 2)),
      _task('call'),
      _task('tomorrow', dueAt: DateTime(2026, 9, 27)),
    ];
    expect(HomeUpNext.pick(today, open).map((t) => t.id), ['call', 'tomorrow', 'friday']);
    expect(HomeUpNext.pick(today, open, limit: 5).map((t) => t.id), ['call', 'tomorrow', 'friday', 'undated']);
  });

  test('with nothing due today the soonest upcoming tasks fill the card', () {
    final open = [_task('b', dueAt: DateTime(2026, 9, 30)), _task('a', dueAt: DateTime(2026, 9, 28))];
    expect(HomeUpNext.pick(const [], open).map((t) => t.id), ['a', 'b']);
  });
}
