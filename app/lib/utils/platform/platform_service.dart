import 'dart:io';

/// A utility class to handle platform-specific service availability
class PlatformService {
  static bool get isMacOS => Platform.isMacOS;
  static bool get isAnalyticsSupported => !Platform.isMacOS;
  static bool get isNotificationSupported => !Platform.isMacOS;
  static bool get isIntercomSupported => !Platform.isMacOS;
  static bool get isMixpanelSupported => !Platform.isMacOS;
  static bool get isInstabugSupported => !Platform.isMacOS;

  /// Execute a function only if the platform supports it
  static T? executeIfSupported<T>(bool isSupported, T Function() function, {T? fallback}) {
    if (isSupported) {
      return function();
    }
    return fallback;
  }

  /// Execute a future function only if the platform supports it
  static Future<T?> executeIfSupportedAsync<T>(bool isSupported, Future<T> Function() function, {T? fallback}) async {
    if (isSupported) {
      return await function();
    }
    return fallback;
  }
}
