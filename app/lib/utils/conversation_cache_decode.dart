import 'dart:convert';

import 'package:omi/backend/schema/conversation.dart';

typedef DecodedConversationCache = ({List<ServerConversation> conversations, List<String> unreadableTypes});

/// Pure worker input/output: no preferences, plugins, logging or account state.
/// Preserve the sync getter's per-entry tolerance without sending raw errors
/// or cache contents back as diagnostics.
DecodedConversationCache decodeConversationCacheSnapshot(List<String> encoded) {
  final conversations = <ServerConversation>[];
  final unreadableTypes = <String>[];
  for (final value in encoded) {
    try {
      final decoded = jsonDecode(value);
      if (decoded is Map<String, dynamic>) {
        conversations.add(ServerConversation.fromJson(decoded));
      } else {
        unreadableTypes.add(decoded.runtimeType.toString());
      }
    } catch (error) {
      unreadableTypes.add(error.runtimeType.toString());
    }
  }
  return (conversations: conversations, unreadableTypes: unreadableTypes);
}
