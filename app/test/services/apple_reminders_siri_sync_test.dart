import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/integrations/apple_reminders_sync_service.dart';

void main() {
  test('confirmed external task updates and deletes reach the index', () async {
    var refreshes = 0;
    final removed = <String>[];
    await applyAppleReminderTaskMutations(
      updates: [
        {'id': 'edited', 'description': 'New title'}
      ],
      deleteIds: ['deleted', 'not-deleted'],
      syncBatch: (_) async => true,
      deleteTask: (id) async => id == 'deleted',
      refreshTaskIndex: () async {
        refreshes++;
      },
      removeFromIndex: (ids) async {
        removed.addAll(ids);
      },
    );
    expect(refreshes, 1);
    expect(removed, ['deleted']);
  });

  test('failed external writes leave the current index intact', () async {
    var refreshes = 0;
    final removed = <String>[];
    await applyAppleReminderTaskMutations(
      updates: [
        {'id': 'edited', 'description': 'Rejected'}
      ],
      deleteIds: ['failed-delete'],
      syncBatch: (_) async => false,
      deleteTask: (_) async => false,
      refreshTaskIndex: () async {
        refreshes++;
      },
      removeFromIndex: (ids) async {
        removed.addAll(ids);
      },
    );
    expect(refreshes, 0);
    expect(removed, isEmpty);
  });
}
