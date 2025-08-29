import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals.dart';

class ConversationSyncService {
  static const Duration _fetchTimeout = Duration(seconds: 30);

  Future<List<SyncedConversationPointer>> processConversationIds({
    required List<String> newConversationIds,
    required List<String> updatedConversationIds,
  }) async {
    debugPrint(
        'ConversationSyncService: Processing ${newConversationIds.length} new and ${updatedConversationIds.length} updated conversations');
    debugPrint('ConversationSyncService: New IDs: $newConversationIds');
    debugPrint('ConversationSyncService: Updated IDs: $updatedConversationIds');

    final List<SyncedConversationPointer> result = [];

    try {
      // Process new conversations
      if (newConversationIds.isNotEmpty) {
        debugPrint('ConversationSyncService: Fetching ${newConversationIds.length} new conversations...');
        final newConversations = await _fetchConversations(newConversationIds);
        final newPointers = _createPointers(newConversations, SyncedConversationType.newConversation);
        debugPrint('ConversationSyncService: Created ${newPointers.length} new conversation pointers');
        result.addAll(newPointers);
      }

      // Process updated conversations
      if (updatedConversationIds.isNotEmpty) {
        debugPrint('ConversationSyncService: Fetching ${updatedConversationIds.length} updated conversations...');
        final updatedConversations = await _fetchConversations(updatedConversationIds);
        final updatedPointers = _createPointers(updatedConversations, SyncedConversationType.updatedConversation);
        debugPrint('ConversationSyncService: Created ${updatedPointers.length} updated conversation pointers');
        result.addAll(updatedPointers);
      }

      debugPrint('ConversationSyncService: Successfully processed ${result.length} total conversations');
      return result;
    } catch (e) {
      debugPrint('ConversationSyncService: Error processing conversations: $e');
      rethrow;
    }
  }

  Future<List<ServerConversation?>> _fetchConversations(List<String> conversationIds) async {
    final futures = conversationIds.map((id) => _fetchSingleConversation(id)).toList();
    return await Future.wait(futures).timeout(_fetchTimeout);
  }

  Future<ServerConversation?> _fetchSingleConversation(String conversationId) async {
    try {
      debugPrint('ConversationSyncService: Fetching conversation $conversationId...');
      final conversation = await getConversationById(conversationId);
      if (conversation != null) {
        debugPrint(
            'ConversationSyncService: Successfully fetched conversation $conversationId (status: ${conversation.status})');
      } else {
        debugPrint('ConversationSyncService: Conversation $conversationId returned null');
      }
      return conversation;
    } catch (e) {
      debugPrint('ConversationSyncService: Failed to fetch conversation $conversationId: $e');
      return null;
    }
  }

  List<SyncedConversationPointer> _createPointers(
    List<ServerConversation?> conversations,
    SyncedConversationType type,
  ) {
    debugPrint('ConversationSyncService: Creating pointers for ${conversations.length} conversations of type $type');

    final validConversations = conversations.where((conversation) => conversation != null).toList();
    debugPrint('ConversationSyncService: ${validConversations.length} non-null conversations');

    final completedConversations =
        validConversations.where((conversation) => conversation!.status == ConversationStatus.completed).toList();
    debugPrint('ConversationSyncService: ${completedConversations.length} completed conversations');

    final pointers = completedConversations.map((conversation) => _createPointer(conversation!, type)).toList();

    debugPrint('ConversationSyncService: Created ${pointers.length} pointers');
    return pointers;
  }

  SyncedConversationPointer _createPointer(ServerConversation conversation, SyncedConversationType type) {
    final date = DateTime(
      conversation.createdAt.year,
      conversation.createdAt.month,
      conversation.createdAt.day,
    );

    return SyncedConversationPointer(
      type: type,
      index: 0, // Simplified index for sync provider
      key: date,
      conversation: conversation,
    );
  }
}
