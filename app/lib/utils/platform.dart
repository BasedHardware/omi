import 'package:flutter/foundation.dart';

class Platform {
  static bool get isWeb => kIsWeb;
  static bool get isNotWeb => !kIsWeb;
  static bool get isIOS => !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;
  static bool get isAndroid => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;
  static bool get isWindows => !kIsWeb && defaultTargetPlatform == TargetPlatform.windows;
  static bool get isMacOS => !kIsWeb && defaultTargetPlatform == TargetPlatform.macOS;
  static bool get isLinux => !kIsWeb && defaultTargetPlatform == TargetPlatform.linux;
  static bool get isMobile => isIOS || isAndroid;
  static bool get isDesktop => isWindows || isMacOS || isLinux;
}
