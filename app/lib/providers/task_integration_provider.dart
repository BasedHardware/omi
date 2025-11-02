import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/services/asana_service.dart';
import 'package:omi/services/clickup_service.dart';
import 'package:omi/services/google_tasks_service.dart';
import 'package:omi/services/todoist_service.dart';
import 'package:omi/utils/platform/platform_service.dart';

class TaskIntegrationProvider extends ChangeNotifier {
  TaskIntegrationApp _selectedApp;

  TaskIntegrationProvider()
      : _selectedApp = TaskIntegrationApp.values.firstWhere(
          (app) => app.key == SharedPreferencesUtil().selectedTaskIntegration,
          orElse: () => PlatformService.isApple ? TaskIntegrationApp.appleReminders : TaskIntegrationApp.googleTasks,
        );

  TaskIntegrationApp get selectedApp => _selectedApp;

  void setSelectedApp(TaskIntegrationApp app) {
    _selectedApp = app;
    SharedPreferencesUtil().selectedTaskIntegration = app.key;
    notifyListeners();
  }

  void loadFromPreferences() {
    final selectedKey = SharedPreferencesUtil().selectedTaskIntegration;
    _selectedApp = TaskIntegrationApp.values.firstWhere(
      (app) => app.key == selectedKey,
      orElse: () => PlatformService.isApple ? TaskIntegrationApp.appleReminders : TaskIntegrationApp.googleTasks,
    );
    notifyListeners();
  }

  /// Check if an app is connected/authenticated
  bool isAppConnected(TaskIntegrationApp app) {
    switch (app) {
      case TaskIntegrationApp.appleReminders:
        return true; // Always connected on Apple platforms
      case TaskIntegrationApp.todoist:
        return TodoistService().isAuthenticated;
      case TaskIntegrationApp.asana:
        return AsanaService().isAuthenticated;
      case TaskIntegrationApp.googleTasks:
        return GoogleTasksService().isAuthenticated;
      case TaskIntegrationApp.clickup:
        return ClickUpService().isAuthenticated;
      default:
        return false;
    }
  }

  /// Trigger a refresh (called after OAuth completes)
  void refresh() {
    notifyListeners();
  }
}
