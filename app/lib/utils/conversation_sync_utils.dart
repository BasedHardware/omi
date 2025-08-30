import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals.dart';

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
    return completedConversations.map((conversation) => _createPointer(conversation!, type)).toList();
  }

  static SyncedConversationPointer _createPointer(ServerConversation conversation, SyncedConversationType type) {
    final date = DateTime(
      conversation.createdAt.year,
      conversation.createdAt.month,
      conversation.createdAt.day,
    );

    return SyncedConversationPointer(
      type: type,
      index: 0,
      key: date,
      conversation: conversation,
    );
  }
}
