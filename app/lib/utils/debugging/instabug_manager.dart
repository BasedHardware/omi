import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

/// Platform-aware manager for Instabug
/// Handles macOS compatibility internally without exposing platform checks
class InstabugManager {
  static final InstabugManager _instance = InstabugManager._internal();
  static InstabugManager get instance => _instance;

  InstabugManager._internal();

  factory InstabugManager() {
    return _instance;
  }

  /// Initialize Instabug with the provided token and settings
  static Future<void> init({
    required String token,
    List<InvocationEvent> invocationEvents = const [InvocationEvent.none],
  }) async {
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isInstabugSupported,
      () => Instabug.init(
        token: token,
        invocationEvents: invocationEvents,
      ),
    );
  }

  /// Set welcome message mode
  Future<void> setWelcomeMessageMode(WelcomeMessageMode mode) async {
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isInstabugSupported,
      () => Instabug.setWelcomeMessageMode(mode),
    );
  }

  /// Identify user with email, name, and user ID
  void identifyUser(String email, String name, String userId) {
    PlatformService.executeIfSupported(
      PlatformService.isInstabugSupported,
      () => Instabug.identifyUser(email, name, userId),
    );
  }

  /// Set color theme
  void setColorTheme(ColorTheme theme) {
    PlatformService.executeIfSupported(
      PlatformService.isInstabugSupported,
      () => Instabug.setColorTheme(theme),
    );
  }

  /// Log info message
  void logInfo(String message) {
    PlatformService.executeIfSupported(
      PlatformService.isInstabugSupported,
      () => InstabugLog.logInfo(message),
    );
  }

  /// Log error message
  void logError(String message) {
    PlatformService.executeIfSupported(
      PlatformService.isInstabugSupported,
      () => InstabugLog.logError(message),
    );
  }

  /// Log warning message
  void logWarn(String message) {
    PlatformService.executeIfSupported(
      PlatformService.isInstabugSupported,
      () => InstabugLog.logWarn(message),
    );
  }

  /// Log debug message
  void logDebug(String message) {
    PlatformService.executeIfSupported(
      PlatformService.isInstabugSupported,
      () => InstabugLog.logDebug(message),
    );
  }

  /// Log verbose message
  void logVerbose(String message) {
    PlatformService.executeIfSupported(
      PlatformService.isInstabugSupported,
      () => InstabugLog.logVerbose(message),
    );
  }

  /// Show bug reporting screen
  void show() {
    PlatformService.executeIfSupported(
      PlatformService.isInstabugSupported,
      () => Instabug.show(),
    );
  }

  /// Set user attribute
  void setUserAttribute(String key, String value) {
    PlatformService.executeIfSupported(
      PlatformService.isInstabugSupported,
      () => Instabug.setUserAttribute(key, value),
    );
  }

  /// Set enabled state
  void setEnabled(bool isEnabled) {
    PlatformService.executeIfSupported(
      PlatformService.isInstabugSupported,
      () => Instabug.setEnabled(isEnabled),
    );
  }

  Future<void> reportCrash(Object exception, StackTrace stackTrace, {Map<String, String>? userAttributes}) async {
    await PlatformService.executeIfSupportedAsync(
      PlatformService.isInstabugSupported,
      () async => await CrashReporting.reportHandledCrash(exception, stackTrace,
          level: NonFatalExceptionLevel.error, userAttributes: userAttributes),
    );
  }

  /// Get navigator observer for navigation tracking
  /// Returns null on unsupported platforms
  NavigatorObserver? getNavigatorObserver() {
    return PlatformService.executeIfSupported(
      PlatformService.isInstabugSupported,
      () => InstabugNavigatorObserver(),
    );
  }

  /// Check if platform supports Instabug
  bool get isSupported => PlatformService.isInstabugSupported;
}
