import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/conversation_provider.dart';

class ConversationSyncUtils {
  static const Duration _fetchTimeout = Duration(seconds: 30);

  static Future<List<SyncedConversationPointer>> processConversationIds({
    required List<String> newConversationIds,
    required List<String> updatedConversationIds,
  }) async {
    final List<SyncedConversationPointer> result = [];

    if (newConversationIds.isNotEmpty) {
      final newConversations = await _fetchConversations(newConversationIds);
      final newPointers = _createPointers(newConversations, SyncedConversationType.newConversation);
      result.addAll(newPointers);
    }

    if (updatedConversationIds.isNotEmpty) {
      final updatedConversations = await _fetchConversations(updatedConversationIds);
      final updatedPointers = _createPointers(updatedConversations, SyncedConversationType.updatedConversation);
      result.addAll(updatedPointers);
    }

    return result;
  }

  static Future<List<ServerConversation?>> _fetchConversations(List<String> conversationIds) async {
    final futures = conversationIds.map((id) => _fetchSingleConversation(id)).toList();
    return await Future.wait(futures).timeout(_fetchTimeout);
  }

  static Future<ServerConversation?> _fetchSingleConversation(String conversationId) async {
    return await getConversationById(conversationId);
  }

  static List<SyncedConversationPointer> _createPointers(
    List<ServerConversation?> conversations,
    SyncedConversationType type,
  ) {
    final validConversations = conversations.where((conversation) => conversation != null).toList();
    final completedConversations =
        validConversations.where((conversation) => conversation!.status == ConversationStatus.completed).toList();
    return completedConversations.map((conversation) => createPointer(conversation!, type)).toList();
  }

  /// The pointer's `key` is handed straight to `ConversationDetailProvider` when
  /// a synced row is tapped, so it must be the key the list groups by:
  /// [conversationLocalDayKey] over `startedAt ?? createdAt`. Reading
  /// `createdAt`'s raw year/month/day instead read *UTC* fields — server
  /// timestamps parse as UTC — so for any viewer off UTC near local midnight the
  /// key matched no group, the tap-time selection silently no-opped and the
  /// detail page opened on whatever conversation was still cached (#10980).
  @visibleForTesting
  static SyncedConversationPointer createPointer(ServerConversation conversation, SyncedConversationType type) {
    final date = conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt);

    return SyncedConversationPointer(type: type, index: 0, key: date, conversation: conversation);
  }
}
