import 'dart:async';

import 'package:omi/utils/logger.dart';

/// Event data for offline sync completion
class SyncCompletedEvent {
  final String jobId;
  final List<String> newConversationIds;
  final List<String> updatedConversationIds;

  SyncCompletedEvent({
    required this.jobId,
    required this.newConversationIds,
    required this.updatedConversationIds,
  });
}

/// Handler for offline_sync_completed FCM data messages.
/// Follows the same pattern as MergeNotificationHandler.
class SyncCompletedNotificationHandler {
  /// Stream controller for sync completed events
  static final StreamController<SyncCompletedEvent> _syncCompletedController =
      StreamController<SyncCompletedEvent>.broadcast();

  /// Stream to listen for sync completed events
  static Stream<SyncCompletedEvent> get onSyncCompleted => _syncCompletedController.stream;

  /// Handle offline_sync_completed FCM data message
  static Future<void> handleSyncCompleted(
    Map<String, dynamic> data,
    String channelKey, {
    bool isAppInForeground = true,
  }) async {
    final jobId = data['job_id'] as String?;
    final newIdsStr = data['new_conversation_ids'] as String?;
    final updatedIdsStr = data['updated_conversation_ids'] as String?;

    if (jobId == null) {
      Logger.debug('[SyncCompleted] Invalid sync completed data');
      return;
    }

    final newIds = newIdsStr?.isNotEmpty == true ? newIdsStr!.split(',') : <String>[];
    final updatedIds = updatedIdsStr?.isNotEmpty == true ? updatedIdsStr!.split(',') : <String>[];

    Logger.debug('[SyncCompleted] Sync completed: job=$jobId new=${newIds.length} updated=${updatedIds.length}');

    // Broadcast the event so SyncProvider can process the results
    _syncCompletedController.add(
      SyncCompletedEvent(
        jobId: jobId,
        newConversationIds: newIds,
        updatedConversationIds: updatedIds,
      ),
    );
  }
}
