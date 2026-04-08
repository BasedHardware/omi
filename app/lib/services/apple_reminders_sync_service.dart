import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/logger.dart';

/// Orchestrates bidirectional Apple Reminders sync on foreground resume.
class AppleRemindersSyncService {
  static final AppleRemindersSyncService _instance = AppleRemindersSyncService._internal();
  factory AppleRemindersSyncService() => _instance;
  AppleRemindersSyncService._internal();

  DateTime? _lastSyncTime;
  bool _isSyncing = false;
  static const _syncCooldown = Duration(seconds: 30);

  final _remindersService = AppleRemindersService();

  Future<void> syncOnForegroundResume() async {
    if (!_remindersService.isAvailable) return;
    if (_isSyncing) return;
    if (_lastSyncTime != null && DateTime.now().difference(_lastSyncTime!) < _syncCooldown) return;
    if (!await _remindersService.hasPermission()) return;

    _isSyncing = true;
    try {
      final syncData = await getPendingSyncItems();
      if (syncData == null) return;

      final exported = await _performOutboundSync(syncData.pendingExport);
      final stats = await _performBidirectionalSync(syncData.syncedItems);
      _lastSyncTime = DateTime.now();

      MixpanelManager().appleRemindersSyncCompleted(
        pendingExported: exported,
        syncedChecked: stats['checked'] ?? 0,
        completionsPulled: stats['completionsPulled'] ?? 0,
        completionsPushed: stats['completionsPushed'] ?? 0,
        titleDuePulled: stats['titleDuePulled'] ?? 0,
        titleDuePushed: stats['titleDuePushed'] ?? 0,
        remindersUnlinked: stats['unlinked'] ?? 0,
      );
    } catch (e) {
      Logger.debug('[AppleRemindersSync] Error: $e');
    } finally {
      _isSyncing = false;
    }
  }

  Future<int> _performOutboundSync(List<ActionItemWithMetadata> pendingItems) async {
    if (pendingItems.isEmpty) return 0;

    final batchUpdates = <Map<String, dynamic>>[];

    for (final item in pendingItems) {
      final calendarItemId = await _remindersService.addReminder(
        title: item.description,
        notes: 'From Omi',
        dueDate: item.dueAt,
        listName: 'Reminders',
      );

      if (calendarItemId != null) {
        batchUpdates.add({
          'id': item.id,
          'exported': true,
          'export_platform': 'apple_reminders',
          'apple_reminder_id': calendarItemId,
        });
      }
    }

    if (batchUpdates.isNotEmpty) {
      await syncBatchUpdate(batchUpdates);
    }
    return batchUpdates.length;
  }

  Future<Map<String, int>> _performBidirectionalSync(List<ActionItemWithMetadata> syncedItems) async {
    final stats = {
      'checked': 0,
      'completionsPulled': 0,
      'completionsPushed': 0,
      'titleDuePulled': 0,
      'titleDuePushed': 0,
      'unlinked': 0,
    };
    if (syncedItems.isEmpty) return stats;

    final mappings = <String, String>{};
    for (final item in syncedItems) {
      if (item.appleReminderId != null) {
        mappings[item.id] = item.appleReminderId!;
      }
    }
    if (mappings.isEmpty) return stats;

    final statuses = await _remindersService.getRemindersStatus(mappings);
    if (statuses.isEmpty) return stats;
    stats['checked'] = statuses.length;

    final backendUpdates = <Map<String, dynamic>>[];
    final deleteIds = <String>[];

    for (final item in syncedItems) {
      if (item.appleReminderId == null) continue;
      final status = statuses[item.id];
      if (status == null) continue;

      final exists = status['exists'] as bool? ?? false;

      if (!exists) {
        deleteIds.add(item.id);
        stats['unlinked'] = stats['unlinked']! + 1;
        continue;
      }

      final reminderCompleted = status['completed'] as bool? ?? false;
      final reminderTitle = status['title'] as String? ?? '';
      final reminderDueDateStr = status['dueDate'] as String?;
      final reminderLastModifiedStr = status['lastModifiedDate'] as String?;

      DateTime? reminderDueDate;
      if (reminderDueDateStr != null) {
        reminderDueDate = DateTime.tryParse(reminderDueDateStr);
      }
      DateTime? reminderLastModified;
      if (reminderLastModifiedStr != null) {
        reminderLastModified = DateTime.tryParse(reminderLastModifiedStr);
      }

      // Completion sync
      if (reminderCompleted && !item.completed) {
        backendUpdates.add({'id': item.id, 'completed': true});
        stats['completionsPulled'] = stats['completionsPulled']! + 1;
      } else if (item.completed && !reminderCompleted) {
        await _remindersService.updateReminderById(item.appleReminderId!, completed: true);
        stats['completionsPushed'] = stats['completionsPushed']! + 1;
      }

      // Title/due date sync (last-writer-wins)
      final appleIsNewer =
          reminderLastModified != null && item.updatedAt != null && reminderLastModified.isAfter(item.updatedAt!);

      if (appleIsNewer) {
        final updates = <String, dynamic>{'id': item.id};
        if (reminderTitle.isNotEmpty && reminderTitle != item.description) {
          updates['description'] = reminderTitle;
        }
        if (_dueDatesAreDifferent(item.dueAt, reminderDueDate)) {
          updates['due_at'] = reminderDueDate?.toUtc().toIso8601String();
        }
        if (updates.length > 1) {
          backendUpdates.add(updates);
          stats['titleDuePulled'] = stats['titleDuePulled']! + 1;
        }
      } else if (item.updatedAt != null &&
          (reminderLastModified == null || item.updatedAt!.isAfter(reminderLastModified))) {
        final needsTitleUpdate = reminderTitle != item.description;
        final needsDueUpdate = _dueDatesAreDifferent(item.dueAt, reminderDueDate);

        if (needsTitleUpdate || needsDueUpdate) {
          await _remindersService.updateReminderById(
            item.appleReminderId!,
            title: needsTitleUpdate ? item.description : null,
            dueDate: needsDueUpdate ? item.dueAt : null,
          );
          stats['titleDuePushed'] = stats['titleDuePushed']! + 1;
        }
      }
    }

    if (backendUpdates.isNotEmpty) {
      await syncBatchUpdate(backendUpdates);
    }
    for (final id in deleteIds) {
      await deleteActionItem(id);
    }
    return stats;
  }

  bool _dueDatesAreDifferent(DateTime? a, DateTime? b) {
    if (a == null && b == null) return false;
    if (a == null || b == null) return true;
    return a.difference(b).abs() > const Duration(seconds: 60);
  }
}
