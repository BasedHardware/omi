import 'dart:io';

import 'package:flutter/foundation.dart';

/// A utility class to handle platform-specific service availability
class PlatformService {
  static bool get isMacOS => Platform.isMacOS;
  static bool get isWindows => Platform.isWindows;
  static bool get isAndroid => Platform.isAndroid;
  static bool get isIOS => Platform.isIOS;
  static bool get isDesktop => isWindows || isMacOS;
  static bool get isMobile => isAndroid || isIOS;
  static bool get isApple => isMacOS || isIOS;
  static bool get isAnalyticsSupported => !(isMacOS || isWindows);
  static bool get isNotificationSupported => !(isMacOS || isWindows);
  static bool get isIntercomSupported => !(isMacOS || isWindows);
  static bool get isMixpanelSupported => !(kIsWeb);
  static bool get isCrashlyticsSupported => !(isWindows || kIsWeb);

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
