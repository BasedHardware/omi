import 'dart:async';

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

  test('index refresh finishes before a confirmed delete can remove its id', () async {
    final refreshGate = Completer<void>();
    final order = <String>[];
    final sync = applyAppleReminderTaskMutations(
      updates: [
        {'id': 'edited', 'description': 'Changed'}
      ],
      deleteIds: ['deleted'],
      syncBatch: (_) async => true,
      deleteTask: (_) async {
        order.add('backend-delete');
        return true;
      },
      refreshTaskIndex: () async {
        order.add('refresh-start');
        await refreshGate.future;
        order.add('refresh-end');
      },
      removeFromIndex: (_) async => order.add('index-delete'),
    );
    await Future<void>.delayed(Duration.zero);
    expect(order, ['refresh-start']);
    refreshGate.complete();
    await sync;
    expect(order, ['refresh-start', 'refresh-end', 'backend-delete', 'index-delete']);
  });
}
