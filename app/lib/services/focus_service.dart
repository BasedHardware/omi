import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';

/// Represents an assistant event from the native side
class AssistantEvent {
  final String type;
  final String? status;
  final String? appOrSite;
  final String? description;
  final String? message;
  final String? assistant;
  final Map<String, dynamic>? task;
  final String? contextSummary;
  final DateTime timestamp;

  AssistantEvent({
    required this.type,
    this.status,
    this.appOrSite,
    this.description,
    this.message,
    this.assistant,
    this.task,
    this.contextSummary,
    required this.timestamp,
  });

  factory AssistantEvent.fromMap(Map<dynamic, dynamic> map) {
    return AssistantEvent(
      type: map['type'] as String? ?? 'unknown',
      status: map['status'] as String?,
      appOrSite: map['appOrSite'] as String?,
      description: map['description'] as String?,
      message: map['message'] as String?,
      assistant: map['assistant'] as String?,
      task: map['task'] != null ? Map<String, dynamic>.from(map['task']) : null,
      contextSummary: map['contextSummary'] as String?,
      timestamp:
          map['timestamp'] != null ? DateTime.tryParse(map['timestamp'] as String) ?? DateTime.now() : DateTime.now(),
    );
  }

  bool get isFocused => status == 'focused';
  bool get isDistracted => status == 'distracted';
  bool get isTaskEvent => type == 'taskExtracted' || type == 'taskUpdated' || type == 'taskCompleted';

  @override
  String toString() {
    if (isTaskEvent) {
      return 'AssistantEvent(type: $type, task: ${task?['title']}, assistant: $assistant)';
    }
    return 'AssistantEvent(type: $type, status: $status, app: $appOrSite, message: $message)';
  }
}

/// Represents an extracted task
class ExtractedTask {
  final String title;
  final String? description;
  final String priority;
  final String sourceApp;
  final String? inferredDeadline;
  final double confidence;

  ExtractedTask({
    required this.title,
    this.description,
    required this.priority,
    required this.sourceApp,
    this.inferredDeadline,
    required this.confidence,
  });

  factory ExtractedTask.fromMap(Map<dynamic, dynamic> map) {
    return ExtractedTask(
      title: map['title'] as String? ?? '',
      description: map['description'] as String?,
      priority: map['priority'] as String? ?? 'medium',
      sourceApp: map['sourceApp'] as String? ?? '',
      inferredDeadline: map['inferredDeadline'] as String?,
      confidence: (map['confidence'] as num?)?.toDouble() ?? 0.0,
    );
  }

  bool get isHighPriority => priority == 'high';
  bool get isMediumPriority => priority == 'medium';
  bool get isLowPriority => priority == 'low';

  @override
  String toString() {
    return 'ExtractedTask(title: $title, priority: $priority, sourceApp: $sourceApp)';
  }
}

/// Backward compatibility: FocusEvent is now AssistantEvent
typedef FocusEvent = AssistantEvent;

/// Current monitoring status
class MonitoringStatus {
  final bool isMonitoring;
  final String? currentApp;
  final String? lastStatus;

  MonitoringStatus({
    required this.isMonitoring,
    this.currentApp,
    this.lastStatus,
  });

  factory MonitoringStatus.fromMap(Map<dynamic, dynamic> map) {
    return MonitoringStatus(
      isMonitoring: map['isMonitoring'] as bool? ?? false,
      currentApp: map['currentApp'] as String?,
      lastStatus: map['lastStatus'] as String?,
    );
  }

  bool get isFocused => lastStatus == 'focused';
  bool get isDistracted => lastStatus == 'distracted';
}

/// Backward compatibility: FocusStatus is now MonitoringStatus
typedef FocusStatus = MonitoringStatus;

/// Represents an assistant configuration
class AssistantInfo {
  final String identifier;
  final String displayName;
  final bool enabled;

  AssistantInfo({
    required this.identifier,
    required this.displayName,
    required this.enabled,
  });

  factory AssistantInfo.fromMap(Map<dynamic, dynamic> map) {
    return AssistantInfo(
      identifier: map['identifier'] as String? ?? '',
      displayName: map['displayName'] as String? ?? '',
      enabled: map['enabled'] as bool? ?? false,
    );
  }
}

/// Service for communicating with the native Proactive Assistants plugin
class FocusService {
  static const _methodChannel = MethodChannel('com.omi.assistants/methods');
  static const _eventChannel = EventChannel('com.omi.assistants/events');

  static final FocusService _instance = FocusService._internal();
  factory FocusService() => _instance;
  FocusService._internal();

  /// Whether focus monitoring is supported on this platform
  static bool get isSupported => Platform.isMacOS;

  StreamSubscription<AssistantEvent>? _eventSubscription;
  final _eventController = StreamController<AssistantEvent>.broadcast();
  final _taskController = StreamController<ExtractedTask>.broadcast();

  /// Stream of all assistant events from the native side
  Stream<AssistantEvent> get events => _eventController.stream;

  /// Stream of focus events (backward compatibility)
  Stream<AssistantEvent> get focusEvents => _eventController.stream.where((e) => !e.isTaskEvent);

  /// Stream of extracted tasks
  Stream<ExtractedTask> get taskEvents => _taskController.stream;

  /// Initialize the service and start listening to events
  void initialize() {
    if (!isSupported) return;

    _eventSubscription?.cancel();

    try {
      _eventSubscription = _eventChannel.receiveBroadcastStream().map((event) {
        return AssistantEvent.fromMap(Map<dynamic, dynamic>.from(event));
      }).listen(
        (event) {
          _eventController.add(event);

          // Also emit task events to the task stream
          if (event.isTaskEvent && event.task != null) {
            _taskController.add(ExtractedTask.fromMap(event.task!));
          }
        },
        onError: (error) {
          print('FocusService: Event stream error: $error');
        },
      );
    } catch (e) {
      print('FocusService: Failed to initialize event stream: $e');
    }
  }

  /// Dispose of resources
  void dispose() {
    _eventSubscription?.cancel();
    _eventController.close();
    _taskController.close();
  }

  /// Start monitoring
  Future<void> startMonitoring() async {
    if (!isSupported) return;
    try {
      await _methodChannel.invokeMethod('startMonitoring');
    } on PlatformException catch (e) {
      print('FocusService: Failed to start monitoring: ${e.message}');
      rethrow;
    }
  }

  /// Stop monitoring
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

  /// Get current monitoring status
  Future<MonitoringStatus?> getCurrentStatus() async {
    if (!isSupported) return null;
    try {
      final result = await _methodChannel.invokeMethod('getCurrentStatus');
      if (result == null) return null;
      return MonitoringStatus.fromMap(Map<dynamic, dynamic>.from(result));
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
  Future<void> triggerGlow({String colorMode = 'focused'}) async {
    if (!isSupported) return;
    try {
      await _methodChannel.invokeMethod('triggerGlow', {'colorMode': colorMode});
    } catch (e) {
      print('FocusService: Failed to trigger glow: $e');
    }
  }

  /// Open the native Settings window
  Future<void> openSettings() async {
    if (!isSupported) return;
    try {
      await _methodChannel.invokeMethod('openSettings');
    } catch (e) {
      print('FocusService: Failed to open settings: $e');
    }
  }

  /// Get current settings
  Future<Map<String, dynamic>?> getSettings() async {
    if (!isSupported) return null;
    try {
      final result = await _methodChannel.invokeMethod('getSettings');
      if (result == null) return null;
      return Map<String, dynamic>.from(result);
    } catch (e) {
      print('FocusService: Failed to get settings: $e');
      return null;
    }
  }

  /// Get list of registered assistants
  Future<List<AssistantInfo>> getAssistants() async {
    if (!isSupported) return [];
    try {
      final result = await _methodChannel.invokeMethod('getAssistants');
      if (result == null) return [];
      return (result as List).map((e) => AssistantInfo.fromMap(Map<dynamic, dynamic>.from(e))).toList();
    } catch (e) {
      print('FocusService: Failed to get assistants: $e');
      return [];
    }
  }

  /// Enable an assistant
  Future<void> enableAssistant(String identifier) async {
    if (!isSupported) return;
    try {
      await _methodChannel.invokeMethod('enableAssistant', {'identifier': identifier});
    } catch (e) {
      print('FocusService: Failed to enable assistant: $e');
    }
  }

  /// Disable an assistant
  Future<void> disableAssistant(String identifier) async {
    if (!isSupported) return;
    try {
      await _methodChannel.invokeMethod('disableAssistant', {'identifier': identifier});
    } catch (e) {
      print('FocusService: Failed to disable assistant: $e');
    }
  }
}
