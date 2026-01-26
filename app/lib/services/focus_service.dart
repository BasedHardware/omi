import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';

/// Represents a focus monitoring event from the native side
class FocusEvent {
  final String type;
  final String? status;
  final String? appOrSite;
  final String? description;
  final String? message;
  final DateTime timestamp;

  FocusEvent({
    required this.type,
    this.status,
    this.appOrSite,
    this.description,
    this.message,
    required this.timestamp,
  });

  factory FocusEvent.fromMap(Map<dynamic, dynamic> map) {
    return FocusEvent(
      type: map['type'] as String? ?? 'unknown',
      status: map['status'] as String?,
      appOrSite: map['appOrSite'] as String?,
      description: map['description'] as String?,
      message: map['message'] as String?,
      timestamp:
          map['timestamp'] != null ? DateTime.tryParse(map['timestamp'] as String) ?? DateTime.now() : DateTime.now(),
    );
  }

  bool get isFocused => status == 'focused';
  bool get isDistracted => status == 'distracted';

  @override
  String toString() {
    return 'FocusEvent(type: $type, status: $status, app: $appOrSite, message: $message)';
  }
}

/// Current focus monitoring status
class FocusStatus {
  final bool isMonitoring;
  final String? currentApp;
  final String? lastStatus;

  FocusStatus({
    required this.isMonitoring,
    this.currentApp,
    this.lastStatus,
  });

  factory FocusStatus.fromMap(Map<dynamic, dynamic> map) {
    return FocusStatus(
      isMonitoring: map['isMonitoring'] as bool? ?? false,
      currentApp: map['currentApp'] as String?,
      lastStatus: map['lastStatus'] as String?,
    );
  }

  bool get isFocused => lastStatus == 'focused';
  bool get isDistracted => lastStatus == 'distracted';
}

/// Service for communicating with the native Focus Monitoring plugin
class FocusService {
  static const _methodChannel = MethodChannel('com.omi.focus/methods');
  static const _eventChannel = EventChannel('com.omi.focus/events');

  static final FocusService _instance = FocusService._internal();
  factory FocusService() => _instance;
  FocusService._internal();

  /// Whether focus monitoring is supported on this platform
  static bool get isSupported => Platform.isMacOS;

  StreamSubscription<FocusEvent>? _eventSubscription;
  final _eventController = StreamController<FocusEvent>.broadcast();

  /// Stream of focus events from the native side
  Stream<FocusEvent> get focusEvents => _eventController.stream;

  /// Initialize the service and start listening to events
  void initialize() {
    if (!isSupported) return;

    _eventSubscription?.cancel();
    _eventSubscription = _eventChannel.receiveBroadcastStream().map((event) {
      return FocusEvent.fromMap(Map<dynamic, dynamic>.from(event));
    }).listen(
      (event) {
        _eventController.add(event);
      },
      onError: (error) {
        print('FocusService: Event stream error: $error');
      },
    );
  }

  /// Dispose of resources
  void dispose() {
    _eventSubscription?.cancel();
    _eventController.close();
  }

  /// Start focus monitoring
  Future<void> startMonitoring() async {
    if (!isSupported) return;
    try {
      await _methodChannel.invokeMethod('startMonitoring');
    } on PlatformException catch (e) {
      print('FocusService: Failed to start monitoring: ${e.message}');
      rethrow;
    }
  }

  /// Stop focus monitoring
  Future<void> stopMonitoring() async {
    if (!isSupported) return;
    try {
      await _methodChannel.invokeMethod('stopMonitoring');
    } on PlatformException catch (e) {
      print('FocusService: Failed to stop monitoring: ${e.message}');
      rethrow;
    }
  }

  /// Check if monitoring is currently active
  Future<bool> isMonitoring() async {
    if (!isSupported) return false;
    try {
      final result = await _methodChannel.invokeMethod('isMonitoring');
      return result as bool? ?? false;
    } catch (e) {
      return false;
    }
  }

  /// Get current focus status
  Future<FocusStatus?> getCurrentStatus() async {
    if (!isSupported) return null;
    try {
      final result = await _methodChannel.invokeMethod('getCurrentStatus');
      if (result == null) return null;
      return FocusStatus.fromMap(Map<dynamic, dynamic>.from(result));
    } catch (e) {
      return null;
    }
  }

  /// Check if screen recording permission is granted
  Future<bool> hasScreenRecordingPermission() async {
    if (!isSupported) return false;
    try {
      final result = await _methodChannel.invokeMethod('hasScreenRecordingPermission');
      return result as bool? ?? false;
    } catch (e) {
      return false;
    }
  }

  /// Request screen recording permission (opens system dialog)
  Future<void> requestScreenRecordingPermission() async {
    if (!isSupported) return;
    try {
      await _methodChannel.invokeMethod('requestScreenRecordingPermission');
    } catch (e) {
      print('FocusService: Failed to request screen recording permission: $e');
    }
  }

  /// Open screen recording settings in System Preferences
  Future<void> openScreenRecordingSettings() async {
    if (!isSupported) return;
    try {
      await _methodChannel.invokeMethod('openScreenRecordingSettings');
    } catch (e) {
      print('FocusService: Failed to open screen recording settings: $e');
    }
  }

  /// Check if notification permission is granted
  Future<bool> hasNotificationPermission() async {
    if (!isSupported) return false;
    try {
      final result = await _methodChannel.invokeMethod('hasNotificationPermission');
      return result as bool? ?? false;
    } catch (e) {
      return false;
    }
  }

  /// Request notification permission
  Future<bool> requestNotificationPermission() async {
    if (!isSupported) return false;
    try {
      final result = await _methodChannel.invokeMethod('requestNotificationPermission');
      return result as bool? ?? false;
    } catch (e) {
      return false;
    }
  }

  /// Manually trigger the glow effect (for testing)
  Future<void> triggerGlow() async {
    if (!isSupported) return;
    try {
      await _methodChannel.invokeMethod('triggerGlow');
    } catch (e) {
      print('FocusService: Failed to trigger glow: $e');
    }
  }
}
