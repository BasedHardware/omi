import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/utils/logger.dart';

/// Orchestrates two-way sync between Omi action items and Apple Reminders.
///
/// Called on app foreground resume. Handles:
/// - Outbound sync: creates reminders for unexported action items
/// - Inbound sync: detects completion status changes in Apple Reminders
class AppleRemindersSyncService {
  static final AppleRemindersSyncService _instance = AppleRemindersSyncService._internal();
  factory AppleRemindersSyncService() => _instance;
  AppleRemindersSyncService._internal();

  final _remindersService = AppleRemindersService();

  DateTime? _lastSyncTime;
  bool _isSyncing = false;
  static const Duration _syncCooldown = Duration(seconds: 30);

  /// Called on foreground resume. Debounced to avoid spamming EventKit.
  Future<void> syncOnForegroundResume() async {
    if (!_remindersService.isAvailable) return;
    if (_isSyncing) return;

    // Debounce: don't sync more than once per 30 seconds
    if (_lastSyncTime != null && DateTime.now().difference(_lastSyncTime!) < _syncCooldown) {
      return;
    }

    // Check permission
    final hasPermission = await _remindersService.hasPermission();
    if (!hasPermission) return;

    _isSyncing = true;
    try {
      final syncData = await getPendingSyncItems(platform: 'apple_reminders');
      if (syncData == null) return;

      await _performOutboundSync(syncData.pendingExport);
      await _performInboundSync(syncData.syncedItems);
      _lastSyncTime = DateTime.now();
    } catch (e) {
      Logger.debug('Apple Reminders sync error: $e');
    } finally {
      _isSyncing = false;
    }
  }

  /// Outbound: create reminders for unexported action items
  Future<void> _performOutboundSync(List<Map<String, dynamic>> pendingExport) async {
    if (pendingExport.isEmpty) return;

    for (final item in pendingExport) {
      final id = item['id'] as String?;
      final description = item['description'] as String?;
      if (id == null || description == null) continue;

      final dueDateStr = item['due_at'] as String?;
      final dueDate = dueDateStr != null ? DateTime.tryParse(dueDateStr) : null;

      try {
        final calendarItemId = await _remindersService.addReminder(
          title: description,
          notes: 'From Omi',
          dueDate: dueDate,
          listName: 'Reminders',
        );

        if (calendarItemId != null) {
          await updateActionItem(
            id,
            exported: true,
            exportPlatform: 'apple_reminders',
            exportDate: DateTime.now(),
            appleReminderId: calendarItemId,
          );
        }
      } catch (e) {
        Logger.debug('Outbound sync failed for item $id: $e');
      }
    }
  }

  /// Inbound: check completion status of synced reminders
  Future<void> _performInboundSync(List<Map<String, dynamic>> syncedItems) async {
    if (syncedItems.isEmpty) return;

    // Build mapping: {actionItemId: calendarItemIdentifier}
    final mappings = <String, String>{};
    final itemStateMap = <String, Map<String, dynamic>>{};

    for (final item in syncedItems) {
      final id = item['id'] as String?;
      final reminderId = item['apple_reminder_id'] as String?;
      if (id == null || reminderId == null || reminderId.isEmpty) continue;
      mappings[id] = reminderId;
      itemStateMap[id] = item;
    }

    if (mappings.isEmpty) return;

    // Get current status from EventKit
    final statuses = await _remindersService.getRemindersStatus(mappings);

    for (final entry in statuses.entries) {
      final actionItemId = entry.key;
      final status = entry.value;
      final itemState = itemStateMap[actionItemId];
      if (itemState == null) continue;

      final exists = status['exists'] as bool? ?? false;
      final reminderCompleted = status['completed'] as bool? ?? false;
      final omiCompleted = itemState['completed'] as bool? ?? false;

      if (!exists) {
        // Reminder was deleted from Apple Reminders — clear the mapping
        try {
          await updateActionItem(actionItemId, appleReminderId: '');
        } catch (e) {
          Logger.debug('Failed to clear apple_reminder_id for $actionItemId: $e');
        }
        continue;
      }

      if (reminderCompleted && !omiCompleted) {
        // Completed in Apple Reminders but not in Omi — sync completion to Omi
        try {
          await updateActionItem(actionItemId, completed: true);
        } catch (e) {
          Logger.debug('Failed to sync completion for $actionItemId: $e');
        }
      } else if (omiCompleted && !reminderCompleted) {
        // Completed in Omi but not in Apple Reminders — sync completion to reminder
        final reminderId = mappings[actionItemId];
        if (reminderId != null) {
          await _remindersService.updateReminderById(reminderId, completed: true);
        }
      }
    }
  }
}
