import 'package:flutter/foundation.dart';

/// Utility class for platform detection
class PlatformUtils {
  /// Check if the current platform is web
  static bool get isWeb => kIsWeb;
  
  /// Check if the current platform is Android
  static bool get isAndroid => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;
  
  /// Check if the current platform is iOS
  static bool get isIOS => !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;
  
  /// Check if the current platform is mobile (Android or iOS)
  static bool get isMobile => isAndroid || isIOS;
  
  /// Get a string representation of the current platform
  static String get platformName {
    if (isWeb) return 'web';
    if (isAndroid) return 'android';
    if (isIOS) return 'ios';
    return 'unknown';
  }
}
