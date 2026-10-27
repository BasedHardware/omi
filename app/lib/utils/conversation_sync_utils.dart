import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/conversation_provider.dart';

class ConversationSyncUtils {
  static const Duration _fetchTimeout = Duration(seconds: 30);

  static Future<List<SyncedConversationPointer>> processConversationIds({
    required List<String> newConversationIds,
    required List<String> updatedConversationIds,
    void Function(String requestedId, ServerConversation conversation)? onConversation,
    Future<ServerConversation?> Function(String id)? fetchConversation,
  }) async {
    final result = <String, SyncedConversationPointer>{};
    Future<void> read(List<String> ids, SyncedConversationType type) async {
      if (ids.isEmpty) return;
      final rows = await _fetchConversations(ids, fetchConversation ?? getConversationById);
      for (var i = 0; i < rows.length; i++) {
        final row = rows[i];
        if (row == null) continue; // Failed/unknown reads cannot remove a prior result.
        onConversation?.call(ids[i], row);
        result.remove(ids[i]);
        result.remove(row.id);
        if (row.status == ConversationStatus.completed && !row.isHiddenFromDefaultList) {
          result[row.id] = createPointer(row, type);
        }
      }
    }

    await read(newConversationIds, SyncedConversationType.newConversation);
    await read(updatedConversationIds, SyncedConversationType.updatedConversation);
    return result.values.toList();
  }

  static Future<List<ServerConversation?>> _fetchConversations(
      List<String> conversationIds, Future<ServerConversation?> Function(String id) fetch) async {
    final futures = conversationIds.map(fetch).toList();
    return await Future.wait(futures).timeout(_fetchTimeout);
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
