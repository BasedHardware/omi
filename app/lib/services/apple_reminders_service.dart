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
      if (call.method == 'markExported') {
        final actionItemId = call.arguments['action_item_id'] as String?;
        if (actionItemId != null) {
          await _markActionItemExported(actionItemId);
        }
      }
    });
  }

  /// Mark an action item as exported after successful Apple Reminders sync
  Future<void> _markActionItemExported(String actionItemId) async {
    try {
      await updateActionItem(
        actionItemId,
        exported: true,
        exportPlatform: 'apple_reminders',
      );
    } catch (e) {
      Logger.debug('Error marking action item as exported: $e');
    }
  }

  /// Check if Apple Reminders is available on this platform
  bool get isAvailable => PlatformService.isApple;

  /// Add a task to Apple Reminders
  /// Returns true if successful, false if failed or permission denied
  Future<bool> addReminder({
    required String title,
    String? notes,
    DateTime? dueDate,
    String? listName,
  }) async {
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

      return result == true;
    } on PlatformException catch (e) {
      Logger.debug('Error adding reminder: ${e.message}');
      return false;
    } catch (e) {
      Logger.debug('Unexpected error adding reminder: $e');
      return false;
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
      final result = await _channel.invokeMethod('getReminders', {
        'listName': listName ?? 'Reminders',
      });

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

  /// Mark a reminder as completed in Apple Reminders
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

  /// Add an action item to Apple Reminders with automatic permission handling
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
    final success = await addReminder(
      title: actionItemDescription,
      notes: 'From Omi',
      listName: 'Reminders',
    );

    return success ? AppleRemindersResult.success : AppleRemindersResult.failed;
  }
}

enum AppleRemindersResult {
  success,
  failed,
  permissionDenied,
  unsupported,
}

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
