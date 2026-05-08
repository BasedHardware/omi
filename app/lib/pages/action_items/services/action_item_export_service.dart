import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/services/asana_service.dart';
import 'package:omi/services/clickup_service.dart';
import 'package:omi/services/google_tasks_service.dart';
import 'package:omi/services/todoist_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

enum ExportResult { success, alreadyExported, failed }

/// Headless single-item exporter used by the bulk-export flow.
///
/// Returns [ExportResult.success] on success, [ExportResult.alreadyExported]
/// when the item was previously exported, or [ExportResult.failed] on auth
/// failure or platform error. The caller (provider) aggregates outcomes into
/// a single snackbar, so this service deliberately stays quiet — no UI side
/// effects.
class ActionItemExportService {
  static Future<ExportResult> export(ActionItemWithMetadata item, TaskIntegrationApp platform) async {
    if (item.exported) return ExportResult.alreadyExported;

    switch (platform) {
      case TaskIntegrationApp.appleReminders:
        return _exportAppleReminders(item);
      case TaskIntegrationApp.todoist:
        return _exportTodoist(item);
      case TaskIntegrationApp.asana:
        return _exportAsana(item);
      case TaskIntegrationApp.googleTasks:
        return _exportGoogleTasks(item);
      case TaskIntegrationApp.clickup:
        return _exportClickUp(item);
      case TaskIntegrationApp.trello:
      case TaskIntegrationApp.monday:
        return ExportResult.failed;
    }
  }

  static Future<ExportResult> _exportTodoist(ActionItemWithMetadata item) async {
    final service = TodoistService();
    if (!service.isAuthenticated) return ExportResult.failed;

    try {
      final ok = await service.createTask(
        content: item.description,
        description: 'From Omi',
        dueDate: item.dueAt,
      );
      if (!ok) return ExportResult.failed;

      final exportTime = DateTime.now();
      await updateActionItem(item.id, exported: true, exportDate: exportTime, exportPlatform: 'todoist');
      MixpanelManager().actionItemExported(actionItemId: item.id, appName: 'Todoist', timestamp: exportTime);
      return ExportResult.success;
    } catch (e) {
      Logger.debug('Todoist bulk export failed for ${item.id}: $e');
      return ExportResult.failed;
    }
  }

  static Future<ExportResult> _exportAsana(ActionItemWithMetadata item) async {
    final service = AsanaService();
    if (!service.isAuthenticated) return ExportResult.failed;

    try {
      final ok = await service.createTask(
        name: item.description,
        notes: 'From Omi',
        dueDate: item.dueAt,
      );
      if (!ok) return ExportResult.failed;

      final exportTime = DateTime.now();
      await updateActionItem(item.id, exported: true, exportDate: exportTime, exportPlatform: 'asana');
      MixpanelManager().actionItemExported(actionItemId: item.id, appName: 'Asana', timestamp: exportTime);
      return ExportResult.success;
    } catch (e) {
      Logger.debug('Asana bulk export failed for ${item.id}: $e');
      return ExportResult.failed;
    }
  }

  static Future<ExportResult> _exportGoogleTasks(ActionItemWithMetadata item) async {
    final service = GoogleTasksService();
    if (!service.isAuthenticated) return ExportResult.failed;

    try {
      final ok = await service.createTask(
        title: item.description,
        notes: 'From Omi',
        dueDate: item.dueAt,
      );
      if (!ok) return ExportResult.failed;

      final exportTime = DateTime.now();
      await updateActionItem(item.id, exported: true, exportDate: exportTime, exportPlatform: 'google_tasks');
      MixpanelManager().actionItemExported(actionItemId: item.id, appName: 'Google Tasks', timestamp: exportTime);
      return ExportResult.success;
    } catch (e) {
      Logger.debug('Google Tasks bulk export failed for ${item.id}: $e');
      return ExportResult.failed;
    }
  }

  static Future<ExportResult> _exportClickUp(ActionItemWithMetadata item) async {
    final service = ClickUpService();
    if (!service.isAuthenticated) return ExportResult.failed;

    try {
      final ok = await service.createTask(
        name: item.description,
        description: 'From Omi',
        dueDate: item.dueAt,
      );
      if (!ok) return ExportResult.failed;

      final exportTime = DateTime.now();
      await updateActionItem(item.id, exported: true, exportDate: exportTime, exportPlatform: 'clickup');
      MixpanelManager().actionItemExported(actionItemId: item.id, appName: 'ClickUp', timestamp: exportTime);
      return ExportResult.success;
    } catch (e) {
      Logger.debug('ClickUp bulk export failed for ${item.id}: $e');
      return ExportResult.failed;
    }
  }

  static Future<ExportResult> _exportAppleReminders(ActionItemWithMetadata item) async {
    if (!PlatformService.isApple) return ExportResult.failed;

    final service = AppleRemindersService();
    try {
      final hasPermission = await service.hasPermission() || await service.requestPermission();
      if (!hasPermission) return ExportResult.failed;

      final calendarItemId = await service.addReminder(
        title: item.description,
        notes: 'From Omi',
        dueDate: item.dueAt,
        listName: 'Reminders',
      );
      if (calendarItemId == null) return ExportResult.failed;

      final exportTime = DateTime.now();
      await updateActionItem(
        item.id,
        exported: true,
        exportDate: exportTime,
        exportPlatform: 'apple_reminders',
        appleReminderId: calendarItemId,
      );
      MixpanelManager().actionItemExported(actionItemId: item.id, appName: 'Apple Reminders', timestamp: exportTime);
      return ExportResult.success;
    } catch (e) {
      Logger.debug('Apple Reminders bulk export failed for ${item.id}: $e');
      return ExportResult.failed;
    }
  }
}
