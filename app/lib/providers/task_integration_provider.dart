import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/services/asana_service.dart';
import 'package:omi/services/clickup_service.dart';
import 'package:omi/services/google_tasks_service.dart';
import 'package:omi/services/todoist_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/platform/platform_service.dart';

class TaskIntegrationProvider extends ChangeNotifier {
  TaskIntegrationApp _selectedApp;
  Map<String, dynamic> _connectionDetails = {};
  bool _isLoading = false;
  bool _hasLoaded = false;

  TaskIntegrationProvider()
      : _selectedApp = PlatformService.isApple ? TaskIntegrationApp.appleReminders : TaskIntegrationApp.googleTasks;

  TaskIntegrationApp get selectedApp => _selectedApp;
  Map<String, dynamic> get connectionDetails => _connectionDetails;
  bool get isLoading => _isLoading;
  bool get hasLoaded => _hasLoaded;

  /// Load default app and connection details from backend
  Future<void> loadFromBackend() async {
    _isLoading = true;
    // Don't notify listeners immediately to avoid setState during build

    try {
      final response = await getTaskIntegrations();
      if (response != null) {
        _connectionDetails = response.integrations;

        // Update service authentication status based on Firebase data
        TodoistService().setAuthenticated(_connectionDetails['todoist']?['connected'] == true &&
            _connectionDetails['todoist']?['access_token'] != null);
        AsanaService().setAuthenticated(
            _connectionDetails['asana']?['connected'] == true && _connectionDetails['asana']?['access_token'] != null,
            userGid: _connectionDetails['asana']?['user_gid']);
        GoogleTasksService().setAuthenticated(_connectionDetails['google_tasks']?['connected'] == true &&
            _connectionDetails['google_tasks']?['access_token'] != null);
        ClickUpService().setAuthenticated(
            _connectionDetails['clickup']?['connected'] == true &&
                _connectionDetails['clickup']?['access_token'] != null,
            userId: _connectionDetails['clickup']?['user_id']);

        if (response.defaultApp != null && response.defaultApp!.isNotEmpty) {
          _selectedApp = TaskIntegrationApp.values.firstWhere(
            (app) => app.key == response.defaultApp,
            orElse: () => PlatformService.isApple ? TaskIntegrationApp.appleReminders : TaskIntegrationApp.googleTasks,
          );
        }
      }
    } catch (e) {
      debugPrint('Error loading task integrations from backend: $e');
    } finally {
      _isLoading = false;
      _hasLoaded = true;
      notifyListeners();
    }
  }

  /// Set default app and save to backend
  Future<void> setSelectedApp(TaskIntegrationApp app) async {
    _selectedApp = app;
    notifyListeners();

    try {
      await setDefaultTaskIntegration(app.key);
    } catch (e) {
      debugPrint('Error saving default task integration: $e');
    }
  }

  /// Save connection details to backend
  Future<bool> saveConnectionDetails(String appKey, Map<String, dynamic> details) async {
    try {
      final success = await saveTaskIntegration(appKey, details);
      if (success) {
        _connectionDetails[appKey] = details;

        // Track successful integration connection
        MixpanelManager().taskIntegrationEnabled(
          appName: appKey,
          success: true,
        );

        notifyListeners();
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('Error saving connection details: $e');
      return false;
    }
  }

  /// Delete connection details from backend
  Future<bool> deleteConnection(String appKey) async {
    try {
      final success = await deleteTaskIntegration(appKey);
      if (success) {
        _connectionDetails.remove(appKey);
        notifyListeners();
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('Error deleting connection: $e');
      return false;
    }
  }

  /// Check if an app is connected/authenticated
  bool isAppConnected(TaskIntegrationApp app) {
    switch (app) {
      case TaskIntegrationApp.appleReminders:
        return true; // Always connected on Apple platforms
      case TaskIntegrationApp.todoist:
        return TodoistService().isAuthenticated;
      case TaskIntegrationApp.asana:
        return AsanaService().isAuthenticated && _connectionDetails.containsKey(app.key);
      case TaskIntegrationApp.googleTasks:
        return GoogleTasksService().isAuthenticated && _connectionDetails.containsKey(app.key);
      case TaskIntegrationApp.clickup:
        return ClickUpService().isAuthenticated && _connectionDetails.containsKey(app.key);
      default:
        return false;
    }
  }

  /// Get connection details for a specific app
  Map<String, dynamic>? getConnectionDetails(String appKey) {
    return _connectionDetails[appKey];
  }

  /// Trigger a refresh (called after OAuth completes)
  void refresh() {
    loadFromBackend();
  }
}
