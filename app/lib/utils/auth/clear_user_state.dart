import 'package:flutter/widgets.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';

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
}
