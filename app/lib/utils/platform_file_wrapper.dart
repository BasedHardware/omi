import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:friend_private/utils/platform_imports.dart';

/// A platform-agnostic wrapper for file operations
/// This class provides a consistent interface for file operations
/// across web and non-web platforms
class PlatformFileWrapper {
  final dynamic _file;
  
  PlatformFileWrapper(this._file);
  
  /// Creates a wrapper from a platform-specific file
  static PlatformFileWrapper? fromPlatformFile(dynamic file) {
    if (file == null) return null;
    return PlatformFileWrapper(file);
  }
  
  /// Get the underlying file object
  dynamic get file => _file;
  
  /// Check if this wrapper contains a valid file
  bool get isValid => _file != null;
  
  /// Get the path of the file
  String get path => kIsWeb ? '' : (_file as File).path;
  
  /// Convert to platform-specific file type for APIs
  dynamic toPlatformFile() {
    if (kIsWeb) {
      return null;
    } else {
      return _file;
    }
  }
  
  /// Create a mock file for web platform
  static PlatformFileWrapper createMockFile(String path) {
    return PlatformFileWrapper(File(path));
  }
}
