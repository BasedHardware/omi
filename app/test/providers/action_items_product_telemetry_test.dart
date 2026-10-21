import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

void main() {
  late ProductTelemetry previousTelemetry;

  setUp(() {
    previousTelemetry = ProductTelemetry.instance;
  });

  tearDown(() {
    ProductTelemetry.instance = previousTelemetry;
  });

  test('task completion emits a successful mutation and value after persistence', () async {
    final events = <RegisteredEvent>[];
    ProductTelemetry.instance = ProductTelemetry(emit: events.add);
    final item = _item();
    final provider = ActionItemsProvider(
      getActionItems: ({
        int limit = 50,
        int offset = 0,
        bool? completed,
        String? conversationId,
        DateTime? startDate,
        DateTime? endDate,
        DateTime? dueStartDate,
        DateTime? dueEndDate,
      }) async =>
          const ActionItemsResponse(actionItems: []),
      updateActionItemRequest: (id, {description, completed, dueAt}) async => item.copyWith(completed: completed),
    );
    addTearDown(provider.dispose);

    expect(await provider.updateActionItemState(item, true), isTrue);
    expect(events.map((event) => event.wireName), [
      'Product Journey Started',
      'Product Journey Outcome',
      'Product Value',
    ]);
    expect(events[1].properties['outcome'], 'success');
    expect(events[2].properties['kind'], 'task_completed');
    expect(events[2].properties['object_id'], 'task-1');
  });

  test('failed task persistence emits failure and no completion value', () async {
    final events = <RegisteredEvent>[];
    ProductTelemetry.instance = ProductTelemetry(emit: events.add);
    final provider = ActionItemsProvider(
      getActionItems: ({
        int limit = 50,
        int offset = 0,
        bool? completed,
        String? conversationId,
        DateTime? startDate,
        DateTime? endDate,
        DateTime? dueStartDate,
        DateTime? dueEndDate,
      }) async =>
          const ActionItemsResponse(actionItems: []),
      updateActionItemRequest: (id, {description, completed, dueAt}) async => null,
    );
    addTearDown(provider.dispose);

    expect(await provider.updateActionItemState(_item(), true), isFalse);
    expect(events.map((event) => event.wireName), ['Product Journey Started', 'Product Journey Outcome']);
    expect(events.last.properties['outcome'], 'failure');
    expect(events.last.properties['failure'], 'server');
  });
}

ActionItemWithMetadata _item() => const ActionItemWithMetadata(
      id: 'task-1',
      description: 'Buy milk',
      completed: false,
    );
