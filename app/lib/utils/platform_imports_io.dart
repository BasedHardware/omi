// Platform-specific imports for non-web platforms
import 'dart:io';
export 'dart:io';

// Re-export platform-specific classes
export 'dart:io' show File, Directory, Platform;

// Helper methods for platform detection
bool get isIOS => Platform.isIOS;
bool get isAndroid => Platform.isAndroid;
bool get isMacOS => Platform.isMacOS;
bool get isWindows => Platform.isWindows;
bool get isLinux => Platform.isLinux;
bool get isFuchsia => Platform.isFuchsia;
