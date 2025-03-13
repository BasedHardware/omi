// This file provides a unified interface for platform-specific imports
// It allows us to use the same code for web and non-web platforms

import 'package:flutter/foundation.dart' show kIsWeb;

// Import platform-specific implementations
import 'dart:io' if (dart.library.html) 'package:friend_private/utils/platform_imports_web.dart';

// Helper method to check if running on web
bool get isRunningOnWeb => kIsWeb;

// Create a platform-agnostic file wrapper
class PlatformFile {
  final dynamic _file;
  
  PlatformFile(this._file);
  
  // Get the underlying file object
  dynamic get file => _file;
  
  // Get the path of the file
  String get path => kIsWeb ? '' : (_file as File).path;
  
  // Check if this is a valid file
  bool get isValid => _file != null;
}

// Helper methods for platform-specific operations
class PlatformUtils {
  // Create a file from a path
  static PlatformFile? createFile(String path) {
    if (kIsWeb) return null;
    return PlatformFile(File(path));
  }
  
  // Check if platform is iOS
  static bool get isIOS => kIsWeb ? false : Platform.isIOS;
  
  // Check if platform is Android
  static bool get isAndroid => kIsWeb ? false : Platform.isAndroid;
}
