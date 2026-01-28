import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/services/focus_service.dart';

/// Provider for focus monitoring and task extraction state management
class FocusProvider extends BaseProvider {
  final FocusService _focusService = FocusService();

  // State
  bool _isMonitoring = false;
  String? _currentApp;
  String? _currentStatus;
  String? _lastMessage;
  final List<AssistantEvent> _history = [];
  final List<ExtractedTask> _extractedTasks = [];
  StreamSubscription<AssistantEvent>? _eventSubscription;
  StreamSubscription<ExtractedTask>? _taskSubscription;

  // Permission states
  bool _hasScreenRecordingPermission = false;
  bool _hasNotificationPermission = false;

  // Assistant states
  List<AssistantInfo> _assistants = [];

  // Getters
  bool get isMonitoring => _isMonitoring;
  String? get currentApp => _currentApp;
  String? get currentStatus => _currentStatus;
  String? get lastMessage => _lastMessage;
  List<AssistantEvent> get history => List.unmodifiable(_history);
  List<ExtractedTask> get extractedTasks => List.unmodifiable(_extractedTasks);
  List<AssistantInfo> get assistants => List.unmodifiable(_assistants);

  bool get isFocused => _currentStatus == 'focused';
  bool get isDistracted => _currentStatus == 'distracted';

  bool get hasScreenRecordingPermission => _hasScreenRecordingPermission;
  bool get hasNotificationPermission => _hasNotificationPermission;

  /// Whether focus monitoring is supported on this platform
  bool get isSupported => Platform.isMacOS;

  /// Initialize the provider
  Future<void> initialize() async {
    if (!isSupported) return;

    _focusService.initialize();

    // Listen to all assistant events
    _eventSubscription = _focusService.events.listen(_handleAssistantEvent);

    // Listen to task events
    _taskSubscription = _focusService.taskEvents.listen(_handleTaskEvent);

    // Check initial permissions
    await checkPermissions();

    // Get current status
    await refreshStatus();

    // Get registered assistants
    await refreshAssistants();
  }

  /// Check all permissions
  Future<void> checkPermissions() async {
    if (!isSupported) return;

    _hasScreenRecordingPermission = await _focusService.hasScreenRecordingPermission();
    _hasNotificationPermission = await _focusService.hasNotificationPermission();
    notifyListeners();
  }

  /// Refresh current monitoring status
  Future<void> refreshStatus() async {
    if (!isSupported) return;

    final status = await _focusService.getCurrentStatus();
    if (status != null) {
      _isMonitoring = status.isMonitoring;
      _currentApp = status.currentApp;
      _currentStatus = status.lastStatus;
      notifyListeners();
    }
  }

  /// Refresh list of registered assistants
  Future<void> refreshAssistants() async {
    if (!isSupported) return;

    _assistants = await _focusService.getAssistants();
    notifyListeners();
  }

  /// Handle incoming assistant events
  void _handleAssistantEvent(AssistantEvent event) {
    debugPrint('FocusProvider: Received event: $event');

    switch (event.type) {
      case 'monitoringStarted':
        _isMonitoring = true;
        break;

      case 'monitoringStopped':
        _isMonitoring = false;
        _currentApp = null;
        _currentStatus = null;
        break;

      case 'statusChange':
        _currentStatus = event.status;
        if (event.message != null) {
          _lastMessage = event.message;
        }
        _addToHistory(event);
        break;

      case 'appSwitch':
        _currentApp = event.appOrSite;
        break;

      case 'alert':
        _lastMessage = event.message;
        _addToHistory(event);
        break;

      case 'refocus':
        // User just refocused - could trigger UI feedback
        break;

      case 'taskExtracted':
      case 'taskUpdated':
      case 'taskCompleted':
        // Task events are handled by _handleTaskEvent
        _addToHistory(event);
        break;
    }

    notifyListeners();
  }

  /// Handle incoming task events
  void _handleTaskEvent(ExtractedTask task) {
    debugPrint('FocusProvider: Received task: $task');

    // Check for duplicates (by title)
    final existingIndex = _extractedTasks.indexWhere(
      (t) => t.title.toLowerCase() == task.title.toLowerCase(),
    );

    if (existingIndex >= 0) {
      // Update existing task
      _extractedTasks[existingIndex] = task;
    } else {
      // Add new task
      _extractedTasks.insert(0, task);
    }

    // Keep only the last 100 tasks
    if (_extractedTasks.length > 100) {
      _extractedTasks.removeLast();
    }

    notifyListeners();
  }

  /// Add event to history (keep last 50)
  void _addToHistory(AssistantEvent event) {
    _history.insert(0, event);
    if (_history.length > 50) {
      _history.removeLast();
    }
  }

  /// Start monitoring
  Future<bool> startMonitoring() async {
    if (!isSupported) return false;

    // Check permission first
    if (!_hasScreenRecordingPermission) {
      final hasPermission = await _focusService.hasScreenRecordingPermission();
      if (!hasPermission) {
        return false;
      }
      _hasScreenRecordingPermission = true;
    }

    setLoadingState(true);
    try {
      await _focusService.startMonitoring();
      _isMonitoring = true;
      notifyListeners();
      return true;
    } catch (e) {
      debugPrint('FocusProvider: Failed to start monitoring: $e');
      return false;
    } finally {
      setLoadingState(false);
    }
  }

  /// Stop monitoring
  Future<void> stopMonitoring() async {
    if (!isSupported) return;

    setLoadingState(true);
    try {
      await _focusService.stopMonitoring();
      _isMonitoring = false;
      _currentApp = null;
      _currentStatus = null;
      notifyListeners();
    } catch (e) {
      debugPrint('FocusProvider: Failed to stop monitoring: $e');
    } finally {
      setLoadingState(false);
    }
  }

  /// Toggle monitoring on/off
  Future<bool> toggleMonitoring() async {
    if (_isMonitoring) {
      await stopMonitoring();
      return false;
    } else {
      return await startMonitoring();
    }
  }

  /// Enable a specific assistant
  Future<void> enableAssistant(String identifier) async {
    if (!isSupported) return;
    await _focusService.enableAssistant(identifier);
    await refreshAssistants();
  }

  /// Disable a specific assistant
  Future<void> disableAssistant(String identifier) async {
    if (!isSupported) return;
    await _focusService.disableAssistant(identifier);
    await refreshAssistants();
  }

  /// Toggle an assistant's enabled state
  Future<void> toggleAssistant(String identifier) async {
    final assistant = _assistants.firstWhere(
      (a) => a.identifier == identifier,
      orElse: () => AssistantInfo(identifier: '', displayName: '', enabled: false),
    );

    if (assistant.identifier.isEmpty) return;

    if (assistant.enabled) {
      await disableAssistant(identifier);
    } else {
      await enableAssistant(identifier);
    }
  }

  /// Request screen recording permission
  Future<void> requestScreenRecordingPermission() async {
    if (!isSupported) return;
    await _focusService.requestScreenRecordingPermission();
  }

  /// Open screen recording settings
  Future<void> openScreenRecordingSettings() async {
    if (!isSupported) return;
    await _focusService.openScreenRecordingSettings();
  }

  /// Request notification permission
  Future<bool> requestNotificationPermission() async {
    if (!isSupported) return false;
    final granted = await _focusService.requestNotificationPermission();
    _hasNotificationPermission = granted;
    notifyListeners();
    return granted;
  }

  /// Trigger glow effect manually (for testing)
  Future<void> triggerGlow({String colorMode = 'focused'}) async {
    if (!isSupported) return;
    await _focusService.triggerGlow(colorMode: colorMode);
  }

  /// Open the native Settings window and start monitoring if not already running
  Future<void> openSettings() async {
    if (!isSupported) return;

    // Start monitoring when opening settings (if not already running)
    if (!_isMonitoring) {
      try {
        await startMonitoring();
      } catch (e) {
        // If monitoring fails to start, still open settings so user can see permissions
        print('FocusProvider: Failed to auto-start monitoring: $e');
      }
    }

    await _focusService.openSettings();
  }

  /// Clear focus history
  void clearHistory() {
    _history.clear();
    notifyListeners();
  }

  /// Clear extracted tasks
  void clearTasks() {
    _extractedTasks.clear();
    notifyListeners();
  }

  /// Remove a specific task
  void removeTask(ExtractedTask task) {
    _extractedTasks.removeWhere((t) => t.title == task.title);
    notifyListeners();
  }

  /// Calculate today's focus score (percentage of focused time)
  double get todayFocusScore {
    if (_history.isEmpty) return 0.0;

    final today = DateTime.now();
    final todayEvents = _history.where((e) {
      return e.timestamp.year == today.year && e.timestamp.month == today.month && e.timestamp.day == today.day;
    }).toList();

    if (todayEvents.isEmpty) return 0.0;

    final focusedCount = todayEvents.where((e) => e.isFocused).length;
    return (focusedCount / todayEvents.length) * 100;
  }

  /// Get high-priority tasks
  List<ExtractedTask> get highPriorityTasks {
    return _extractedTasks.where((t) => t.isHighPriority).toList();
  }

  /// Get tasks from a specific app
  List<ExtractedTask> tasksFromApp(String appName) {
    return _extractedTasks.where((t) => t.sourceApp == appName).toList();
  }

  @override
  void dispose() {
    _eventSubscription?.cancel();
    _taskSubscription?.cancel();
    super.dispose();
  }
}
