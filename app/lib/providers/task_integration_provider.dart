import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/services/integrations/connection_read.dart';

import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/services/integrations/apple_reminders_service.dart';
import 'package:omi/services/integrations/asana_service.dart';
import 'package:omi/services/integrations/clickup_service.dart';
import 'package:omi/services/integrations/google_tasks_service.dart';
import 'package:omi/services/integrations/todoist_service.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

class TaskIntegrationProvider extends ChangeNotifier {
  final Future<bool> Function(String appKey) _setDefaultTaskIntegration;
  final Future<TaskIntegrationsResponse?> Function() _fetchStatus;
  final Duration statusTimeout;
  Future<void>? _inFlightLoad;
  int _readGeneration = 0;
  final _activeReads = <ConnectionRead<Object?>>{};
  bool _hasLoadError = false;
  TaskIntegrationApp _selectedApp;
  Map<String, dynamic> _connectionDetails = {};
  bool _isLoading = false;
  bool _hasLoaded = false;
  bool _appleRemindersPermission = false;
  bool _appleRemindersPermissionManuallySet = false;
  int _sessionGeneration = 0;

  TaskIntegrationProvider({
    Future<bool> Function(String appKey)? setDefaultTaskIntegrationFn,
    Future<TaskIntegrationsResponse?> Function()? fetchStatus,
    this.statusTimeout = const Duration(seconds: 45),
  })  : _setDefaultTaskIntegration = setDefaultTaskIntegrationFn ?? setDefaultTaskIntegration,
        _fetchStatus = fetchStatus ?? getTaskIntegrations,
        _selectedApp = PlatformService.isApple ? TaskIntegrationApp.appleReminders : TaskIntegrationApp.googleTasks;

  TaskIntegrationApp get selectedApp => _selectedApp;
  Map<String, dynamic> get connectionDetails => _connectionDetails;
  bool get isLoading => _isLoading;
  bool get hasLoaded => _hasLoaded;
  bool get hasLoadError => _hasLoadError;

  /// Load default app and connection details from backend
  Future<void> loadFromBackend({bool forceRefresh = false, bool silent = false}) {
    final existing = _inFlightLoad;
    if (existing != null && !forceRefresh) return existing;
    late final Future<void> started;
    started = _loadFromBackendBody(++_readGeneration, silent: silent).whenComplete(() {
      if (identical(_inFlightLoad, started)) _inFlightLoad = null;
    });
    _inFlightLoad = started;
    return started;
  }

  Future<void> _loadFromBackendBody(int readGeneration, {required bool silent}) async {
    final generation = _sessionGeneration;
    bool isCurrent() => generation == _sessionGeneration && readGeneration == _readGeneration;
    if (!silent) {
      _isLoading = true;
      notifyListeners();
    }

    try {
      final read = ConnectionRead(_fetchStatus, statusTimeout);
      _activeReads.add(read);
      TaskIntegrationsResponse? response;
      try {
        response = await read.future;
      } finally {
        _activeReads.remove(read);
      }
      if (!isCurrent()) return;
      if (response == null) {
        _hasLoadError = true;
        return;
      }
      // Validate the entire status snapshot before mutating cached grants.
      for (final key in ['todoist', 'asana', 'google_tasks', 'clickup']) {
        final value = response.integrations[key];
        if (value != null && (value is! Map<String, dynamic> || value['connected'] is! bool)) {
          _hasLoadError = true;
          return;
        }
      }
      _hasLoadError = false;
      _connectionDetails = Map<String, dynamic>.from(response.integrations);

      // The server status DTO deliberately omits provider secrets. Its connected
      // verdict is authoritative; do not require a token on the client.
      TodoistService().setAuthenticated(
        _connectionDetails['todoist']?['connected'] == true,
      );
      AsanaService().setAuthenticated(
        _connectionDetails['asana']?['connected'] == true,
        userGid: _connectionDetails['asana']?['user_gid'],
      );
      GoogleTasksService().setAuthenticated(
        _connectionDetails['google_tasks']?['connected'] == true,
      );
      ClickUpService().setAuthenticated(
        _connectionDetails['clickup']?['connected'] == true,
        userId: _connectionDetails['clickup']?['user_id'],
      );

      if (PlatformService.isApple && !_appleRemindersPermissionManuallySet) {
        final permission = await AppleRemindersService().hasPermission();
        if (!isCurrent()) return;
        _appleRemindersPermission = permission;
        // Ensure backend has connected status for Apple Reminders if permission is granted
        if (_appleRemindersPermission && _connectionDetails['apple_reminders']?['connected'] != true) {
          await saveConnectionDetails('apple_reminders', {'connected': true});
        }
      }
      _appleRemindersPermissionManuallySet = false;

      final defaultApp = response.defaultApp;
      if (defaultApp != null && defaultApp.isNotEmpty) {
        _selectedApp = TaskIntegrationApp.values.firstWhere(
          (app) => app.key == defaultApp,
          orElse: () => PlatformService.isApple ? TaskIntegrationApp.appleReminders : TaskIntegrationApp.googleTasks,
        );
      }
    } catch (e) {
      if (!isCurrent()) return;
      _hasLoadError = true;
      Logger.debug('Error loading task integration statuses');
    } finally {
      if (isCurrent()) {
        _isLoading = false;
        _hasLoaded = true;
        notifyListeners();
      }
    }
  }

  /// Default writes run one at a time in the order they were chosen, so the
  /// server ends on the user's latest choice; only that choice publishes.
  Future<void> _defaultWrites = Future.value();
  int _defaultChoice = 0;

  /// Set default app and save to backend.
  ///
  /// Only publishes the selection after the server accepts it so local state
  /// cannot claim a default that was never persisted. A save made while an
  /// earlier one is in flight waits for it; a choice replaced before it is sent
  /// is skipped, and a replaced choice never publishes.
  Future<bool> setSelectedApp(TaskIntegrationApp app) async {
    final generation = _sessionGeneration;
    final choice = ++_defaultChoice;
    final previous = _defaultWrites;
    final written = Completer<void>();
    _defaultWrites = written.future;
    try {
      await previous;
      if (generation != _sessionGeneration || choice != _defaultChoice) return false;
      final read = ConnectionRead(() => _setDefaultTaskIntegration(app.key), statusTimeout);
      _activeReads.add(read);
      bool success;
      try {
        success = await read.future;
      } finally {
        _activeReads.remove(read);
      }
      if (generation != _sessionGeneration || choice != _defaultChoice || !success) return false;

      // A status read issued before this write cannot restore the prior default.
      _readGeneration++;
      _inFlightLoad = null;
      _isLoading = false;
      _selectedApp = app;
      notifyListeners();
      return true;
    } catch (e) {
      Logger.debug('Error saving default task integration: $e');
      return false;
    } finally {
      written.complete();
    }
  }

  /// Save connection details to backend
  Future<bool> saveConnectionDetails(String appKey, Map<String, dynamic> details) async {
    final generation = _sessionGeneration;
    try {
      final success = await saveTaskIntegration(appKey, details);
      if (generation != _sessionGeneration) return false;
      if (success) {
        _connectionDetails[appKey] = details;
        notifyListeners();
        return true;
      }
      return false;
    } catch (e) {
      Logger.debug('Error saving connection details: $e');
      return false;
    }
  }

  /// Delete connection details from backend
  Future<bool> deleteConnection(String appKey) async {
    final generation = _sessionGeneration;
    try {
      final success = await deleteTaskIntegration(appKey);
      if (generation != _sessionGeneration) return false;
      if (success) {
        _connectionDetails.remove(appKey);
        notifyListeners();
        return true;
      }
      return false;
    } catch (e) {
      Logger.debug('Error deleting connection: $e');
      return false;
    }
  }

  /// Check if an app is connected/authenticated
  bool isAppConnected(TaskIntegrationApp app) {
    switch (app) {
      case TaskIntegrationApp.appleReminders:
        return _appleRemindersPermission;
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

  Future<void> updateAppleRemindersPermission({bool? granted}) async {
    final generation = _sessionGeneration;
    if (PlatformService.isApple) {
      if (granted != null) {
        _appleRemindersPermission = granted;
        _appleRemindersPermissionManuallySet = true;
      } else {
        _appleRemindersPermission = await AppleRemindersService().hasPermission();
        if (generation != _sessionGeneration) return;
      }
      if (generation != _sessionGeneration) return;
      notifyListeners();
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

  void clearUserData() {
    _sessionGeneration++;
    _readGeneration++;
    for (final read in _activeReads) {
      read.cancel();
    }
    _activeReads.clear();
    _inFlightLoad = null;
    _hasLoadError = false;
    _selectedApp = PlatformService.isApple ? TaskIntegrationApp.appleReminders : TaskIntegrationApp.googleTasks;
    _connectionDetails = {};
    _isLoading = false;
    _hasLoaded = false;
    _appleRemindersPermission = false;
    _appleRemindersPermissionManuallySet = false;
    TodoistService().setAuthenticated(false);
    AsanaService().setAuthenticated(false);
    GoogleTasksService().setAuthenticated(false);
    ClickUpService().setAuthenticated(false);
    notifyListeners();
  }

  @override
  void dispose() {
    _sessionGeneration++;
    _readGeneration++;
    for (final read in _activeReads) {
      read.cancel();
    }
    _activeReads.clear();
    super.dispose();
  }
}
