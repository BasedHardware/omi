import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/utils/logger.dart';

/// Local identity is distinct from the server conversation it is waiting for.
class OptimisticProcessingConversation extends ServerConversation {
  OptimisticProcessingConversation({this.targetConversationId})
      : super(
          id: OptimisticProcessingPlaceholder.id,
          createdAt: DateTime.now(),
          structured: Structured('', ''),
          status: ConversationStatus.processing,
        );

  final String? targetConversationId;
}

/// Local-only optimistic row shown on Conversations immediately after Process Now.
class OptimisticProcessingPlaceholder {
  static const String id = '0';
  static const Duration timeout = Duration(minutes: 2);

  static ServerConversation conversation({String? targetConversationId}) =>
      OptimisticProcessingConversation(targetConversationId: targetConversationId);

  static bool keepOnProcessingList(ServerConversation conversation) {
    final stillProcessing =
        conversation.status == ConversationStatus.processing || conversation.status == ConversationStatus.merging;
    return stillProcessing;
  }

  static Future<void> handleFailure({
    required CaptureExternalActions actions,
    required bool removePlaceholder,
    required Object error,
    required StackTrace stack,
    required Future<void> Function(String message, StackTrace stack) report,
  }) async {
    if (removePlaceholder) {
      try {
        actions.removeProcessingConversation(id);
      } catch (cleanupError) {
        Logger.debug('Process Now placeholder cleanup failed: ${cleanupError.runtimeType}');
      }
    }
    Logger.debug('Process Now result handling failed: ${error.runtimeType}');
    await reportDetachedFailure('capture_process_now', error, stack, report);
  }

  static Future<void> reportDetachedFailure(String operation, Object error, StackTrace stack,
      Future<void> Function(String message, StackTrace stack) report) async {
    try {
      await report('$operation: ${error.runtimeType}', stack);
    } catch (reporterError) {
      Logger.debug('Detached capture error report failed: ${reporterError.runtimeType}');
    }
  }

  /// Apply a `processInProgressConversation` result to the Conversations lists.
  ///
  /// Returns the confirmed conversation id when WAL stamp/sync should run.
  /// Only server processing/merging stays on the processing skeleton. A
  /// completed row is settled even without a title; a null result removes the placeholder and
  /// tells [onNoConversation] why nothing was kept.
  static Future<String?> applyProcessResult({
    required CreateConversationResponse? result,
    required CaptureExternalActions actions,
    required Future<void> Function(ServerConversation conversation, List<ServerMessage> messages) onCreated,
    ProcessAbsence? absence,
    void Function(ProcessAbsence absence)? onNoConversation,
    bool removePlaceholder = true,
  }) async {
    if (result == null || result.conversation == null) {
      if (removePlaceholder) actions.removeProcessingConversation(id);
      // A 200 with no conversation is a confirmed empty delete. A null HTTP
      // result without an explicit absence is a transport failure. A 404 stays
      // [ProcessAbsence.notFound] so the caller can wait for a conversation
      // that was already finalized.
      final resolved = absence ?? (result == null ? ProcessAbsence.transport : ProcessAbsence.emptyBody);
      onNoConversation?.call(resolved);
      return null;
    }
    final response = result;
    final conversation = response.conversation!;
    if (removePlaceholder) actions.removeProcessingConversation(id);
    if (keepOnProcessingList(conversation)) {
      actions.addProcessingConversation(conversation);
      return conversation.id;
    }
    if (conversation.status != ConversationStatus.completed) return conversation.id;
    conversation.isNew = true;
    await onCreated(conversation, response.messages);
    return conversation.id;
  }
}
