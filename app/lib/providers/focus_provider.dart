import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/services/focus_service.dart';

/// Provider for focus monitoring state management
class FocusProvider extends BaseProvider {
  final FocusService _focusService = FocusService();

  // State
  bool _isMonitoring = false;
  String? _currentApp;
  String? _currentStatus;
  String? _lastMessage;
  final List<FocusEvent> _history = [];
  StreamSubscription<FocusEvent>? _eventSubscription;

  // Permission states
  bool _hasScreenRecordingPermission = false;
  bool _hasNotificationPermission = false;

  // Getters
  bool get isMonitoring => _isMonitoring;
  String? get currentApp => _currentApp;
  String? get currentStatus => _currentStatus;
  String? get lastMessage => _lastMessage;
  List<FocusEvent> get history => List.unmodifiable(_history);

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

    // Listen to focus events
    _eventSubscription = _focusService.focusEvents.listen(_handleFocusEvent);

    // Check initial permissions
    await checkPermissions();

    // Get current status
    await refreshStatus();
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

  /// Handle incoming focus events
  void _handleFocusEvent(FocusEvent event) {
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
    }

    notifyListeners();
  }

  /// Add event to history (keep last 50)
  void _addToHistory(FocusEvent event) {
    _history.insert(0, event);
    if (_history.length > 50) {
      _history.removeLast();
    }
  }

  /// Start focus monitoring
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

  /// Stop focus monitoring
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
  Future<void> triggerGlow() async {
    if (!isSupported) return;
    await _focusService.triggerGlow();
  }

  /// Clear history
  void clearHistory() {
    _history.clear();
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

  @override
  void dispose() {
    _eventSubscription?.cancel();
    super.dispose();
  }
}
