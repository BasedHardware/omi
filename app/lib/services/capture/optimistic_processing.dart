import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';

/// Local-only optimistic row shown on Conversations immediately after Process Now.
class OptimisticProcessingPlaceholder {
  static const String id = '0';

  static ServerConversation conversation() {
    return ServerConversation(
      id: id,
      createdAt: DateTime.now(),
      structured: Structured('', ''),
      status: ConversationStatus.processing,
    );
  }

  static bool hasTitleAndEmoji(ServerConversation conversation) {
    final structured = conversation.structured;
    return structured.title.trim().isNotEmpty && structured.emoji.trim().isNotEmpty;
  }

  static bool keepOnProcessingList(ServerConversation conversation) {
    final stillProcessing =
        conversation.status == ConversationStatus.processing || conversation.status == ConversationStatus.merging;
    return stillProcessing || !hasTitleAndEmoji(conversation);
  }

  /// Apply a `processInProgressConversation` result to the Conversations lists.
  ///
  /// Returns the confirmed conversation id when WAL stamp/sync should run.
  /// A contentless or still-processing row stays on the processing skeleton
  /// until title + emoji arrive; a null result removes the placeholder and
  /// tells [onNoConversation] why nothing was kept.
  static Future<String?> applyProcessResult({
    required CreateConversationResponse? result,
    required CaptureExternalActions actions,
    required Future<void> Function(ServerConversation conversation, List<ServerMessage> messages) onCreated,
    ProcessAbsence? absence,
    void Function(EmptyRecordingReason reason)? onNoConversation,
  }) async {
    final missing = reasonForMissingConversation(
      hasResponse: result != null,
      hasConversation: result?.conversation != null,
      absence: absence,
    );
    if (missing != null || result == null || result.conversation == null) {
      actions.removeProcessingConversation(id);
      if (missing != null) onNoConversation?.call(missing);
      return null;
    }
    final response = result;
    final conversation = response.conversation!;
    actions.removeProcessingConversation(id);
    if (keepOnProcessingList(conversation)) {
      actions.addProcessingConversation(conversation);
      return conversation.id;
    }
    conversation.isNew = true;
    await onCreated(conversation, response.messages);
    return conversation.id;
  }
}
