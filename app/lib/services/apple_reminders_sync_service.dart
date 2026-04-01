import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/utils/logger.dart';

/// Orchestrates two-way sync between Omi action items and Apple Reminders.
///
/// Called on app foreground resume. Handles:
/// - Outbound sync: creates reminders for unexported action items (only items
///   created after the user connected Apple Reminders)
/// - Bidirectional sync: syncs all fields (title, due date, completion) both ways
///   for items that already have an apple_reminder_id
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

    if (_lastSyncTime != null && DateTime.now().difference(_lastSyncTime!) < _syncCooldown) {
      return;
    }

    final hasPermission = await _remindersService.hasPermission();
    if (!hasPermission) return;

    _isSyncing = true;
    try {
      final syncData = await getPendingSyncItems(platform: 'apple_reminders');
      if (syncData == null) return;

      await _performOutboundSync(syncData.pendingExport);
      await _performBidirectionalSync(syncData.syncedItems);
      _lastSyncTime = DateTime.now();
    } catch (e) {
      Logger.debug('Apple Reminders sync error: $e');
    } finally {
      _isSyncing = false;
    }
  }

  /// Outbound: create reminders for unexported action items.
  /// The backend only returns items created after the user connected Apple Reminders,
  /// so this won't dump old items when the integration is first enabled.
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

  /// Bidirectional sync for items that already have an apple_reminder_id.
  ///
  /// Compares EventKit reminder state with Omi state and pushes diffs both ways.
  /// Uses Omi's updated_at vs _lastSyncTime to determine direction:
  /// - If Omi was updated since last sync → push all Omi fields to reminder
  /// - Otherwise → pull all reminder fields to Omi
  /// - Completion is always merged: if either side completed, both become completed
  Future<void> _performBidirectionalSync(List<Map<String, dynamic>> syncedItems) async {
    if (syncedItems.isEmpty) return;

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

    final statuses = await _remindersService.getRemindersStatus(mappings);

    for (final entry in statuses.entries) {
      final actionItemId = entry.key;
      final status = entry.value;
      final itemState = itemStateMap[actionItemId];
      if (itemState == null) continue;

      final exists = status['exists'] as bool? ?? false;

      if (!exists) {
        // Reminder was deleted from Apple Reminders — clear the mapping
        try {
          await updateActionItem(actionItemId, appleReminderId: '');
        } catch (e) {
          Logger.debug('Failed to clear apple_reminder_id for $actionItemId: $e');
        }
        continue;
      }

      final reminderId = mappings[actionItemId]!;

      // Current state on both sides
      final reminderCompleted = status['completed'] as bool? ?? false;
      final omiCompleted = itemState['completed'] as bool? ?? false;
      final reminderTitle = status['title'] as String? ?? '';
      final omiDescription = itemState['description'] as String? ?? '';
      final reminderDueDateStr = status['dueDate'] as String?;
      final omiDueDateStr = itemState['due_at'] as String?;
      final reminderDueDate = reminderDueDateStr != null ? DateTime.tryParse(reminderDueDateStr) : null;
      final omiDueDate = omiDueDateStr != null ? DateTime.tryParse(omiDueDateStr) : null;

      final titleDiffers = reminderTitle.isNotEmpty && reminderTitle != omiDescription;
      final dueDateDiffers = _dueDatesAreDifferent(reminderDueDate, omiDueDate);
      final completionDiffers = reminderCompleted != omiCompleted;

      if (!titleDiffers && !dueDateDiffers && !completionDiffers) continue;

      // Determine direction: did Omi change since last sync?
      final omiUpdatedAtStr = itemState['updated_at'] as String?;
      final omiUpdatedAt = omiUpdatedAtStr != null ? DateTime.tryParse(omiUpdatedAtStr) : null;
      final omiChangedSinceLastSync =
          _lastSyncTime != null && omiUpdatedAt != null && omiUpdatedAt.isAfter(_lastSyncTime!);

      if (omiChangedSinceLastSync) {
        // Omi was edited since last sync → push Omi state to reminder
        await _pushOmiToReminder(reminderId, omiDescription, omiDueDate, omiCompleted, reminderCompleted);
      } else {
        // Reminder may have changed → pull reminder state to Omi
        await _pullReminderToOmi(
          actionItemId,
          reminderId,
          reminderTitle,
          reminderDueDate,
          reminderCompleted,
          omiDescription,
          omiDueDate,
          omiCompleted,
        );
      }
    }
  }

  /// Push Omi fields to Apple Reminder (Omi is the source of truth for this item)
  Future<void> _pushOmiToReminder(
    String reminderId,
    String omiTitle,
    DateTime? omiDueDate,
    bool omiCompleted,
    bool reminderCompleted,
  ) async {
    await _remindersService.updateReminderById(
      reminderId,
      title: omiTitle,
      dueDate: omiDueDate,
      completed: omiCompleted || reminderCompleted, // if either completed, mark completed
    );
  }

  /// Pull Apple Reminder fields to Omi (Reminder is the source of truth for this item).
  /// Collects all diffs into a single PATCH call.
  Future<void> _pullReminderToOmi(
    String actionItemId,
    String reminderId,
    String reminderTitle,
    DateTime? reminderDueDate,
    bool reminderCompleted,
    String omiDescription,
    DateTime? omiDueDate,
    bool omiCompleted,
  ) async {
    bool? patchCompleted;
    String? patchDescription;
    DateTime? patchDueAt;
    bool patchClearDueAt = false;
    bool needsOmiUpdate = false;

    // Completion: merge — if either side completed, both become completed
    if (reminderCompleted && !omiCompleted) {
      patchCompleted = true;
      needsOmiUpdate = true;
    } else if (omiCompleted && !reminderCompleted) {
      // Omi completed but reminder not → push completion to reminder
      await _remindersService.updateReminderById(reminderId, completed: true);
    }

    // Title: pull from reminder
    if (reminderTitle.isNotEmpty && reminderTitle != omiDescription) {
      patchDescription = reminderTitle;
      needsOmiUpdate = true;
    }

    // Due date: pull from reminder
    if (_dueDatesAreDifferent(reminderDueDate, omiDueDate)) {
      if (reminderDueDate != null) {
        patchDueAt = reminderDueDate;
      } else {
        patchClearDueAt = true;
      }
      needsOmiUpdate = true;
    }

    if (needsOmiUpdate) {
      try {
        await updateActionItem(
          actionItemId,
          completed: patchCompleted,
          description: patchDescription,
          dueAt: patchDueAt,
          clearDueAt: patchClearDueAt,
        );
      } catch (e) {
        Logger.debug('Failed to sync reminder→Omi for $actionItemId: $e');
      }
    }
  }

  /// Check if two due dates are meaningfully different (ignoring seconds/milliseconds).
  /// EventKit only stores year/month/day/hour/minute in dueDateComponents.
  bool _dueDatesAreDifferent(DateTime? a, DateTime? b) {
    if (a == null && b == null) return false;
    if (a == null || b == null) return true;
    return a.year != b.year || a.month != b.month || a.day != b.day || a.hour != b.hour || a.minute != b.minute;
  }
}
