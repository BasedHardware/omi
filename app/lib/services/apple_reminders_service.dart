import 'package:flutter/services.dart';
import 'package:omi/utils/platform/platform_service.dart';

class AppleRemindersService {
  static const _channel = MethodChannel('com.omi.apple_reminders');

  static final AppleRemindersService _instance = AppleRemindersService._internal();
  factory AppleRemindersService() => _instance;
  AppleRemindersService._internal();

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
      print('Error adding reminder: ${e.message}');
      return false;
    } catch (e) {
      print('Unexpected error adding reminder: $e');
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
      print('Error checking reminders permission: $e');
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
      print('Error requesting reminders permission: $e');
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
      print('Error fetching reminders: $e');
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
      print('Error completing reminder: $e');
      return false;
    }
  }

  /// Update an existing reminder's title and notes
  Future<bool> updateReminder({
    required String oldTitle,
    required String newTitle,
    String? newNotes,
    String? listName,
  }) async {
    if (!isAvailable) {
      throw UnsupportedError('Apple Reminders is only available on iOS and macOS');
    }

    try {
      final result = await _channel.invokeMethod('updateReminder', {
        'oldTitle': oldTitle,
        'newTitle': newTitle,
        'newNotes': newNotes,
        'listName': listName ?? 'Reminders',
      });

      return result == true;
    } on PlatformException catch (e) {
      print('Error updating reminder: ${e.message}');
      return false;
    } catch (e) {
      print('Unexpected error updating reminder: $e');
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

  /// Update an action item's title in Apple Reminders with automatic permission handling
  Future<AppleRemindersResult> updateActionItem({
    required String oldTitle,
    required String newTitle,
  }) async {
    if (!isAvailable) {
      return AppleRemindersResult.unsupported;
    }

    // Check permission first
    bool hasPermission = await this.hasPermission();
    if (!hasPermission) {
      return AppleRemindersResult.permissionDenied;
    }

    // Update the reminder
    final success = await updateReminder(
      oldTitle: oldTitle,
      newTitle: newTitle,
      newNotes: 'From Omi',
      listName: 'Reminders',
    );

    return success ? AppleRemindersResult.success : AppleRemindersResult.failed;
  }

  /// Smart update that tries multiple strategies to find and update the reminder
  Future<AppleRemindersResult> updateActionItemSmart({
    required String oldTitle,
    required String newTitle,
  }) async {
    if (!isAvailable) {
      return AppleRemindersResult.unsupported;
    }

    // Check permission first
    bool hasPermission = await this.hasPermission();
    if (!hasPermission) {
      return AppleRemindersResult.permissionDenied;
    }

    try {
      final result = await _channel.invokeMethod('updateReminderSmart', {
        'oldTitle': oldTitle,
        'newTitle': newTitle,
        'newNotes': 'From Omi',
        'listName': 'Reminders',
      });

      return result == true ? AppleRemindersResult.success : AppleRemindersResult.failed;
    } on PlatformException catch (e) {
      print('Error updating reminder smartly: ${e.message}');
      return AppleRemindersResult.failed;
    } catch (e) {
      print('Unexpected error updating reminder smartly: $e');
      return AppleRemindersResult.failed;
    }
  }

  /// Delete an existing reminder by title
  Future<bool> deleteReminder({
    required String title,
    String? listName,
  }) async {
    if (!isAvailable) {
      throw UnsupportedError('Apple Reminders is only available on iOS and macOS');
    }

    try {
      final result = await _channel.invokeMethod('deleteReminder', {
        'title': title,
        'listName': listName ?? 'Reminders',
      });

      return result == true;
    } on PlatformException catch (e) {
      print('Error deleting reminder: ${e.message}');
      return false;
    } catch (e) {
      print('Unexpected error deleting reminder: $e');
      return false;
    }
  }

  /// Delete an action item from Apple Reminders with automatic permission handling
  Future<AppleRemindersResult> deleteActionItem(String actionItemDescription) async {
    if (!isAvailable) {
      return AppleRemindersResult.unsupported;
    }

    // Check permission first
    bool hasPermission = await this.hasPermission();
    if (!hasPermission) {
      return AppleRemindersResult.permissionDenied;
    }

    // Delete the reminder
    final success = await deleteReminder(
      title: actionItemDescription,
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
