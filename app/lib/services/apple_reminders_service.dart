import 'package:flutter/services.dart';

import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

class AppleRemindersService {
  static const _channel = MethodChannel('com.omi.apple_reminders');

  static final AppleRemindersService _instance = AppleRemindersService._internal();
  factory AppleRemindersService() => _instance;
  AppleRemindersService._internal() {
    _initBackgroundSyncHandler();
  }

  void _initBackgroundSyncHandler() {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'markExportedBatch') {
        // New format: mappings with calendarItemIdentifier
        final mappings = (call.arguments['mappings'] as List?)?.cast<Map<Object?, Object?>>() ?? [];
        await Future.wait(
          mappings.map((m) {
            final actionItemId = m['actionItemId'] as String?;
            final calendarItemId = m['calendarItemIdentifier'] as String?;
            if (actionItemId != null) {
              return _markActionItemExported(actionItemId, calendarItemId);
            }
            return Future.value();
          }),
        );
      } else if (call.method == 'markExported') {
        final actionItemId = call.arguments['action_item_id'] as String?;
        if (actionItemId != null) {
          await _markActionItemExported(actionItemId, null);
        }
      }
    });
  }

  /// Mark an action item as exported after successful Apple Reminders sync
  Future<void> _markActionItemExported(String actionItemId, String? calendarItemIdentifier) async {
    try {
      await updateActionItem(
        actionItemId,
        exported: true,
        exportPlatform: 'apple_reminders',
        appleReminderId: calendarItemIdentifier,
      );
    } catch (e) {
      Logger.debug('Error marking action item as exported: $e');
    }
  }

  /// Trigger native sync from foreground when FCM data message is received.
  /// Forwards the raw FCM data payload to the native side for processing,
  /// then marks successfully created reminders as exported in the backend.
  Future<void> triggerSyncFromFCM(Map<String, dynamic> data) async {
    if (!isAvailable) return;
    try {
      final result = await _channel.invokeMethod('syncFromFCM', data);
      // New format: list of {"actionItemId": "...", "calendarItemIdentifier": "..."}
      final mappings = (result as List?)?.cast<Map<Object?, Object?>>() ?? [];
      await Future.wait(
        mappings.map((m) {
          final actionItemId = m['actionItemId'] as String?;
          final calendarItemId = m['calendarItemIdentifier'] as String?;
          if (actionItemId != null) {
            return _markActionItemExported(actionItemId, calendarItemId);
          }
          return Future.value();
        }),
      );
    } catch (e) {
      Logger.debug('Error triggering sync from FCM: $e');
    }
  }

  /// Check if Apple Reminders is available on this platform
  bool get isAvailable => PlatformService.isApple;

  /// Add a task to Apple Reminders.
  /// Returns the calendarItemIdentifier on success, null on failure.
  Future<String?> addReminder({required String title, String? notes, DateTime? dueDate, String? listName}) async {
    if (!isAvailable) {
      throw UnsupportedError('Apple Reminders is only available on iOS and macOS');
    }

    try {
      final result = await _channel.invokeMethod('addReminder', {
        'title': title,
        'notes': notes,
        'dueDate': dueDate?.millisecondsSinceEpoch,
        'listName': listName ?? 'Reminders',
      });

      // result is now the calendarItemIdentifier string (or null on failure)
      return result as String?;
    } on PlatformException catch (e) {
      Logger.debug('Error adding reminder: ${e.message}');
      return null;
    } catch (e) {
      Logger.debug('Unexpected error adding reminder: $e');
      return null;
    }
  }

  /// Check if the app has permission to access reminders
  Future<bool> hasPermission() async {
    if (!isAvailable) return false;

    try {
      final result = await _channel.invokeMethod('hasPermission');
      return result == true;
    } catch (e) {
      Logger.debug('Error checking reminders permission: $e');
      return false;
    }
  }

  /// Request permission to access reminders
  Future<bool> requestPermission() async {
    if (!isAvailable) return false;

    try {
      final result = await _channel.invokeMethod('requestPermission');
      return result == true;
    } catch (e) {
      Logger.debug('Error requesting reminders permission: $e');
      return false;
    }
  }

  /// Get existing reminders from the specified list
  Future<List<String>> getExistingReminders({String? listName}) async {
    if (!isAvailable) return [];

    try {
      final result = await _channel.invokeMethod('getReminders', {'listName': listName ?? 'Reminders'});

      if (result is List) {
        return result.cast<String>();
      }
      return [];
    } catch (e) {
      Logger.debug('Error fetching reminders: $e');
      return [];
    }
  }

  /// Check if a specific reminder exists
  Future<bool> reminderExists(String title, {String? listName}) async {
    final existingReminders = await getExistingReminders(listName: listName);
    return existingReminders.contains(title);
  }

  /// Mark a reminder as completed in Apple Reminders (legacy: by title match)
  Future<bool> completeReminder(String title, {String? listName}) async {
    if (!isAvailable) return false;

    try {
      final result = await _channel.invokeMethod('completeReminder', {
        'title': title,
        'listName': listName ?? 'Reminders',
      });

      return result == true;
    } catch (e) {
      Logger.debug('Error completing reminder: $e');
      return false;
    }
  }

  /// Get completion status of reminders by their calendarItemIdentifier.
  /// Input: map of {actionItemId: calendarItemIdentifier}
  /// Output: map of {actionItemId: {exists: bool, completed: bool, title: String, completionDate: String?}}
  Future<Map<String, Map<String, dynamic>>> getRemindersStatus(Map<String, String> mappings) async {
    if (!isAvailable || mappings.isEmpty) return {};

    try {
      final result = await _channel.invokeMethod('getRemindersStatus', {'mappings': mappings});
      if (result is Map) {
        return result.map((key, value) => MapEntry(key.toString(), (value as Map).cast<String, dynamic>()));
      }
      return {};
    } catch (e) {
      Logger.debug('Error getting reminders status: $e');
      return {};
    }
  }

  /// Update a reminder by its calendarItemIdentifier
  Future<Map<String, dynamic>> updateReminderById(
    String calendarItemIdentifier, {
    String? title,
    String? notes,
    DateTime? dueDate,
    bool? completed,
  }) async {
    if (!isAvailable) return {'success': false, 'exists': false};

    try {
      final args = <String, dynamic>{'calendarItemIdentifier': calendarItemIdentifier};
      if (title != null) args['title'] = title;
      if (notes != null) args['notes'] = notes;
      if (dueDate != null) args['dueDate'] = dueDate.millisecondsSinceEpoch;
      if (completed != null) args['completed'] = completed;

      final result = await _channel.invokeMethod('updateReminder', args);
      if (result is Map) {
        return result.cast<String, dynamic>();
      }
      return {'success': false, 'exists': false};
    } catch (e) {
      Logger.debug('Error updating reminder: $e');
      return {'success': false, 'exists': false};
    }
  }

  /// Delete a reminder by its calendarItemIdentifier
  Future<Map<String, dynamic>> deleteReminderById(String calendarItemIdentifier) async {
    if (!isAvailable) return {'success': false, 'existed': false};

    try {
      final result = await _channel.invokeMethod('deleteReminder', {'calendarItemIdentifier': calendarItemIdentifier});
      if (result is Map) {
        return result.cast<String, dynamic>();
      }
      return {'success': false, 'existed': false};
    } catch (e) {
      Logger.debug('Error deleting reminder: $e');
      return {'success': false, 'existed': false};
    }
  }

  /// Add an action item to Apple Reminders with automatic permission handling.
  /// Returns the calendarItemIdentifier on success.
  Future<AppleRemindersResult> addActionItem(String actionItemDescription) async {
    if (!isAvailable) {
      return AppleRemindersResult.unsupported;
    }

    // Check permission first
    bool hasPermission = await this.hasPermission();
    if (!hasPermission) {
      hasPermission = await requestPermission();
      if (!hasPermission) {
        return AppleRemindersResult.permissionDenied;
      }
    }

    // Add the reminder
    final calendarItemId = await addReminder(title: actionItemDescription, notes: 'From Omi', listName: 'Reminders');

    return calendarItemId != null ? AppleRemindersResult.success : AppleRemindersResult.failed;
  }
}

enum AppleRemindersResult { success, failed, permissionDenied, unsupported }

extension AppleRemindersResultExtension on AppleRemindersResult {
  String get message {
    switch (this) {
      case AppleRemindersResult.success:
        return 'Added to Apple Reminders';
      case AppleRemindersResult.failed:
        return 'Failed to add to Reminders';
      case AppleRemindersResult.permissionDenied:
        return 'Permission denied for Reminders';
      case AppleRemindersResult.unsupported:
        return 'Apple Reminders not available';
    }
  }

  bool get isSuccess => this == AppleRemindersResult.success;
}
