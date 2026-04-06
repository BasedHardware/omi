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
        final mappings = (call.arguments['mappings'] as List?)?.cast<Map>() ?? [];
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

  Future<void> _markActionItemExported(String actionItemId, String? appleReminderId) async {
    try {
      await updateActionItem(
        actionItemId,
        exported: true,
        exportPlatform: 'apple_reminders',
        appleReminderId: appleReminderId,
      );
    } catch (e) {
      Logger.debug('Error marking action item as exported: $e');
    }
  }

  /// Trigger native sync from foreground when FCM data message is received.
  Future<void> triggerSyncFromFCM(Map<String, dynamic> data) async {
    if (!isAvailable) return;
    try {
      final result = await _channel.invokeMethod('syncFromFCM', data);
      final mappings = (result as List?)?.cast<Map>() ?? [];
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

      if (result is String) {
        return result;
      }
      return null;
    } on PlatformException catch (e) {
      Logger.debug('Error adding reminder: ${e.message}');
      return null;
    } catch (e) {
      Logger.debug('Unexpected error adding reminder: $e');
      return null;
    }
  }

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

  /// Batch lookup reminder status by calendarItemIdentifier.
  Future<Map<String, Map<String, dynamic>>> getRemindersStatus(Map<String, String> mappings) async {
    if (!isAvailable) return {};

    try {
      final result = await _channel.invokeMethod('getRemindersStatus', {'mappings': mappings});
      if (result is Map) {
        return result.map((key, value) => MapEntry(key as String, Map<String, dynamic>.from(value as Map)));
      }
      return {};
    } catch (e) {
      Logger.debug('Error getting reminders status: $e');
      return {};
    }
  }

  /// Update a reminder by calendarItemIdentifier.
  Future<bool> updateReminderById(
    String calendarItemIdentifier, {
    String? title,
    bool? completed,
    DateTime? dueDate,
  }) async {
    if (!isAvailable) return false;

    try {
      final args = <String, dynamic>{'calendarItemIdentifier': calendarItemIdentifier};
      if (title != null) args['title'] = title;
      if (completed != null) args['completed'] = completed;
      if (dueDate != null) args['dueDate'] = dueDate.millisecondsSinceEpoch;

      final result = await _channel.invokeMethod('updateReminder', args);
      return (result as Map?)?['success'] == true;
    } catch (e) {
      Logger.debug('Error updating reminder: $e');
      return false;
    }
  }

  /// Delete a reminder by calendarItemIdentifier. Idempotent.
  Future<bool> deleteReminderById(String calendarItemIdentifier) async {
    if (!isAvailable) return false;

    try {
      final result = await _channel.invokeMethod('deleteReminder', {'calendarItemIdentifier': calendarItemIdentifier});
      return (result as Map?)?['success'] == true;
    } catch (e) {
      Logger.debug('Error deleting reminder: $e');
      return false;
    }
  }

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

  Future<bool> reminderExists(String title, {String? listName}) async {
    final existingReminders = await getExistingReminders(listName: listName);
    return existingReminders.contains(title);
  }

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

  Future<AppleRemindersResult> addActionItem(String actionItemDescription) async {
    if (!isAvailable) {
      return AppleRemindersResult.unsupported;
    }

    bool hasPermission = await this.hasPermission();
    if (!hasPermission) {
      hasPermission = await requestPermission();
      if (!hasPermission) {
        return AppleRemindersResult.permissionDenied;
      }
    }

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
