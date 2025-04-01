import 'dart:io';

import 'package:flutter/foundation.dart';

typedef PlatformCallback = void Function();

/// A utility class to handle platform-specific code execution.
/// It provides a method to execute different callbacks based on the platform
/// the code is running on (Android, iOS, Web, or MacOS).
/// It uses the `kIsWeb` constant from the `foundation` package to check if
/// the code is running on the web, and the `Platform` class from the `dart:io`
/// library to check for Android, iOS, and MacOS platforms.
class PlatformHandler {
  /// Executes the appropriate callback based on the platform.
  /// If the platform is not recognized, it executes the `defaultAction` callback.
  ///
  /// - `defaultAction`: A callback to execute if the platform is not recognized.
  /// - `onAndroid`: A callback to execute if the platform is Android.
  /// - `onIOS`: A callback to execute if the platform is iOS.
  /// - `onWeb`: A callback to execute if the platform is Web.
  /// - `onMacOS`: A callback to execute if the platform is MacOS.
  static void optional({
    required PlatformCallback defaultAction,
    PlatformCallback? onAndroid,
    PlatformCallback? onIOS,
    PlatformCallback? onWeb,
    PlatformCallback? onMacOS,
  }) {
    if (kIsWeb && onWeb != null) {
      onWeb.call();
    } else if (Platform.isAndroid && onAndroid != null) {
      onAndroid.call();
    } else if (Platform.isIOS && onIOS != null) {
      onIOS.call();
    } else if (Platform.isMacOS && onMacOS != null) {
      onMacOS.call();
    } else {
      defaultAction.call();
    }
  }

  /// Executes the appropriate callback based on the platform.
  /// If the platform is not recognized, it does nothing.
  ///
  /// - `onAndroid`: A callback to execute if the platform is Android.
  /// - `onIOS`: A callback to execute if the platform is iOS.
  /// - `onWeb`: A callback to execute if the platform is Web.
  /// - `onMacOS`: A callback to execute if the platform is MacOS.
  static void require({
    required PlatformCallback onAndroid,
    required PlatformCallback onIOS,
    required PlatformCallback onWeb,
    required PlatformCallback onMacOS,
  }) {
    if (kIsWeb) {
      onWeb.call();
    } else if (Platform.isAndroid) {
      onAndroid.call();
    } else if (Platform.isIOS) {
      onIOS.call();
    } else if (Platform.isMacOS) {
      onMacOS.call();
    }
  }
}
