import 'dart:io';

import 'package:flutter/foundation.dart';

/// A utility class to handle platform-specific service availability across
/// mobile and desktop runtimes.
class PlatformService {
  static bool get isAndroid => Platform.isAndroid;
  static bool get isIOS => Platform.isIOS;
  static bool get isMobile => isAndroid || isIOS;
  // True when running as a native desktop app (macOS, Linux, Windows).
  // Used to gate desktop-only recording paths (e.g. system audio capture).
  static bool get isDesktop => Platform.isMacOS || Platform.isLinux || Platform.isWindows;
  static bool get isApple => isIOS;
  static bool get isAnalyticsSupported => true;
  static bool get isNotificationSupported => true;
  static bool get isIntercomSupported => true;
  static bool get isMixpanelSupported => !(kIsWeb);
  static bool get isMixpanelNativelySupported => isAndroid || isIOS;
  static bool get isCrashlyticsSupported => true;

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
