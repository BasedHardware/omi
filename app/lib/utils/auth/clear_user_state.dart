import 'package:flutter/widgets.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';

/// Wipes in-memory user-scoped state from every provider so a subsequent
/// login (different account) doesn't briefly render the previous user's
/// conversations, memories, messages, action items, etc.
void clearAllUserState(BuildContext context) {
  context.read<ConversationProvider>().clearUserData();
  context.read<MessageProvider>().clearUserData();
  context.read<MemoriesProvider>().clearUserData();
  context.read<CaptureProvider>().clearUserData();
  context.read<AppProvider>().clearUserData();
  context.read<PeopleProvider>().clearUserData();
  context.read<ActionItemsProvider>().clearUserData();
  context.read<UsageProvider>().clearUserData();
  context.read<UserProvider>().clearUserData();
  context.read<FolderProvider>().clearUserData();
  context.read<HomeProvider>().clearUserData();
  context.read<GoalsProvider>().clearUserData();
  context.read<PhoneCallProvider>().clearUserData();
  context.read<TaskIntegrationProvider>().clearUserData();
  context.read<IntegrationProvider>().clearUserData();
  context.read<McpProvider>().clearUserData();
  context.read<PaymentMethodProvider>().clearUserData();
}
