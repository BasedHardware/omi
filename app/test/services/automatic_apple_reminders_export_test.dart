import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/integrations/automatic_apple_reminders_export.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const owner = AuthSessionSnapshot(ownerUid: 'alice', generation: 1);
  late bool current;
  late bool permission;
  late List<String> writes;
  late TaskIntegrationsResponse? status;
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    current = true;
    permission = true;
    writes = [];
    status = TaskIntegrationsResponse(defaultApp: 'apple_reminders', integrations: {
      'apple_reminders': {'connected': true},
      'todoist': {'connected': true},
    });
  });
  AutomaticAppleRemindersExport exporter({
    Future<TaskIntegrationsResponse?> Function(bool Function())? read,
    Future<bool> Function()? checkPermission,
    Future<String?> Function(ActionItemWithMetadata)? create,
  }) =>
      AutomaticAppleRemindersExport(
        available: () => true,
        capture: () => owner,
        isCurrent: (_) => current,
        status: read ??
            (canSend) async {
              expect(canSend(), isTrue);
              return status;
            },
        permission: checkPermission ?? () async => permission,
        create: create ??
            (item) async {
              writes.add('native:${item.id}');
              return 'eventkit-id';
            },
        acknowledge: (id, reminder, canSend) async {
          expect(canSend(), isTrue);
          writes.add('ack:$id:$reminder');
          return true;
        },
      );
  ActionItemWithMetadata item() =>
      const ActionItemWithMetadata(id: 'task', description: 'Fixture task', completed: false);

  for (final destination in ['todoist', 'asana', 'google_tasks', 'unknown', '', null]) {
    test('permission alone cannot export a task selected for $destination to Apple', () async {
      status = TaskIntegrationsResponse(defaultApp: destination, integrations: status!.integrations);
      await exporter().export(item(), canContinue: () => true);
      expect(writes, isEmpty);
    });
  }
  test('a confirmed Apple selection creates and acknowledges one reminder', () async {
    await exporter().export(item(), canContinue: () => true);
    expect(writes, ['native:task', 'ack:task:eventkit-id']);
  });
  test('unknown status and failed reads never fall back to Apple', () async {
    status = null;
    await exporter().export(item(), canContinue: () => true);
    await exporter(read: (_) => Future.error(StateError('offline'))).export(item(), canContinue: () => true);
    expect(writes, isEmpty);
  });
  test('disconnected selection, denied permission and retired tasks do not export', () async {
    status = TaskIntegrationsResponse(defaultApp: 'apple_reminders', integrations: {
      'apple_reminders': {'connected': false}
    });
    await exporter().export(item(), canContinue: () => true);
    status = TaskIntegrationsResponse(defaultApp: 'apple_reminders', integrations: {
      'apple_reminders': {'connected': true}
    });
    permission = false;
    await exporter().export(item(), canContinue: () => true);
    permission = true;
    await exporter().export(item().copyWith(completed: true), canContinue: () => true);
    await exporter().export(item().copyWith(exported: true, exportPlatform: 'todoist'), canContinue: () => true);
    expect(writes, isEmpty);
  });
  test('an account change during status or permission cannot create a reminder', () async {
    final pending = Completer<TaskIntegrationsResponse?>();
    final work = exporter(read: (_) => pending.future).export(item(), canContinue: () => true);
    current = false;
    pending.complete(status);
    await work;
    expect(writes, isEmpty);
    current = true;
    await exporter(checkPermission: () async {
      current = false;
      return true;
    }).export(item(), canContinue: () => true);
    expect(writes, isEmpty);
  });
  test('late native completion cannot mark a replacement account exported', () async {
    await exporter(create: (_) async {
      current = false;
      writes.add('native:old-owner');
      return 'old-reminder';
    }).export(item(), canContinue: () => true);
    expect(writes, ['native:old-owner']);
  });

  Future<ActionItemsResponse?> emptyTasks({
    int limit = 50,
    int offset = 0,
    bool? completed,
    String? conversationId,
    DateTime? startDate,
    DateTime? endDate,
    DateTime? dueStartDate,
    DateTime? dueEndDate,
  }) async =>
      const ActionItemsResponse(actionItems: []);

  test('the real create provider routes through the saved default without altering its task receipt', () async {
    var reads = 0;
    final gate = Completer<TaskIntegrationsResponse?>();
    final provider = ActionItemsProvider(
      getActionItems: emptyTasks,
      createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async => item(),
      automaticAppleRemindersExport: exporter(read: (_) {
        reads++;
        return gate.future;
      }),
    );
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    final saved = await provider.createActionItem(description: 'Fixture task');
    expect(saved?.id, 'task');
    expect(reads, 1);
    gate.complete(TaskIntegrationsResponse(defaultApp: 'todoist', integrations: status!.integrations));
    for (var i = 0; i < 8; i++) {
      await Future<void>.value();
    }
    expect(writes, isEmpty);
    expect(provider.actionItems.map((row) => row.id), ['task']);
  });

  test('clearing the real provider while the destination is loading cancels its export', () async {
    final gate = Completer<TaskIntegrationsResponse?>();
    final provider = ActionItemsProvider(
      getActionItems: emptyTasks,
      createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) async => item(),
      automaticAppleRemindersExport: exporter(read: (_) => gate.future),
    );
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    await provider.createActionItem(description: 'Fixture task');
    provider.clearUserData();
    gate.complete(status);
    for (var i = 0; i < 8; i++) {
      await Future<void>.value();
    }
    expect(writes, isEmpty);
    expect(provider.actionItems, isEmpty);
  });
}
