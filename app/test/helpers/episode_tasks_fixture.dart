import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/services/integrations/automatic_apple_reminders_export.dart';

ActionItemsProvider episodeTasks({CreateActionItemRequest? create}) => ActionItemsProvider(
      getActionItems: (
              {limit = 50,
              offset = 0,
              completed,
              conversationId,
              startDate,
              endDate,
              dueStartDate,
              dueEndDate}) async =>
          const ActionItemsResponse(actionItems: []),
      createActionItemRequest: create ??
          ({required description, dueAt, conversationId, completed = false, idempotencyKey}) async =>
              ActionItemWithMetadata(
                  id: 'synthetic-task', description: description, completed: completed, conversationId: conversationId),
      automaticAppleRemindersExport: AutomaticAppleRemindersExport(available: () => false),
    );
