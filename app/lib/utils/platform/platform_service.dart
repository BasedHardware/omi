import 'dart:io';

import 'package:flutter/foundation.dart';

/// A utility class to handle platform-specific service availability.
/// The app targets mobile only (iOS/Android). Desktop lives in desktop/.
class PlatformService {
  static bool get isAndroid => Platform.isAndroid;
  static bool get isIOS => Platform.isIOS;
  static bool get isMobile => isAndroid || isIOS;
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
