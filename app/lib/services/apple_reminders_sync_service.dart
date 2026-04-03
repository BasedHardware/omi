import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/services/apple_reminders_service.dart';
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

      await _performOutboundSync(syncData.pendingExport);
      await _performBidirectionalSync(syncData.syncedItems);
      _lastSyncTime = DateTime.now();
    } catch (e) {
      Logger.debug('[AppleRemindersSync] Error: $e');
    } finally {
      _isSyncing = false;
    }
  }

  Future<void> _performOutboundSync(List<ActionItemWithMetadata> pendingItems) async {
    if (pendingItems.isEmpty) return;

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
  }

  Future<void> _performBidirectionalSync(List<ActionItemWithMetadata> syncedItems) async {
    if (syncedItems.isEmpty) return;

    final mappings = <String, String>{};
    for (final item in syncedItems) {
      if (item.appleReminderId != null) {
        mappings[item.id] = item.appleReminderId!;
      }
    }
    if (mappings.isEmpty) return;

    final statuses = await _remindersService.getRemindersStatus(mappings);
    if (statuses.isEmpty) return;

    final backendUpdates = <Map<String, dynamic>>[];

    for (final item in syncedItems) {
      if (item.appleReminderId == null) continue;
      final status = statuses[item.id];
      if (status == null) continue;

      final exists = status['exists'] as bool? ?? false;

      if (!exists) {
        backendUpdates.add({'id': item.id, 'exported': false, 'apple_reminder_id': ''});
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
      } else if (item.completed && !reminderCompleted) {
        await _remindersService.updateReminderById(item.appleReminderId!, completed: true);
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
        }
      }
    }

    if (backendUpdates.isNotEmpty) {
      await syncBatchUpdate(backendUpdates);
    }
  }

  bool _dueDatesAreDifferent(DateTime? a, DateTime? b) {
    if (a == null && b == null) return false;
    if (a == null || b == null) return true;
    return a.difference(b).abs() > const Duration(seconds: 60);
  }
}
