import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/conversations/home_rows_health.dart';

void main() {
  tearDown(HomeRowsHealth.resetForTests);

  test('an empty home is reported, and a rebuild of the same count is not', () {
    final seen = <int>[];
    HomeRowsHealth.report = seen.add;
    final t = DateTime.utc(2026, 11, 3, 8);

    HomeRowsHealth.note(0, now: t);
    HomeRowsHealth.note(0, now: t.add(const Duration(seconds: 10)));
    HomeRowsHealth.note(3, now: t.add(const Duration(seconds: 20)));

    expect(seen, [0, 3]);
  });
}
