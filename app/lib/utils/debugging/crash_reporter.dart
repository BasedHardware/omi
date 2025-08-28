import 'package:flutter/material.dart';

/// Abstract interface for crash reporting functionality
abstract class CrashReporter {
  /// Initialize the crash reporter
  static Future<void> init() async {
    throw UnimplementedError('init() must be implemented');
  }

  /// Identify user with email, name, and user ID
  void identifyUser(String email, String name, String userId);

  /// Log info message
  void logInfo(String message);

  /// Log error message
  void logError(String message);

  /// Log warning message
  void logWarn(String message);

  /// Log debug message
  void logDebug(String message);

  /// Log verbose message
  void logVerbose(String message);

  /// Set user attribute
  void setUserAttribute(String key, String value);

  /// Set enabled state
  void setEnabled(bool isEnabled);

  /// Report a handled crash
  Future<void> reportCrash(Object exception, StackTrace stackTrace, {Map<String, String>? userAttributes});

  /// Get navigator observer for navigation tracking
  NavigatorObserver? getNavigatorObserver();

  /// Check if platform supports crash reporting
  bool get isSupported;
}
