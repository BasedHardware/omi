// Platform-specific imports for web platform
import 'dart:typed_data';
import 'package:flutter/painting.dart' show FileImage;

// Export Uint8List for web
export 'dart:typed_data' show Uint8List;

// Mock Platform class for web
class Platform {
  static bool get isIOS => false;
  static bool get isAndroid => false;
  static bool get isMacOS => false;
  static bool get isWindows => false;
  static bool get isLinux => false;
  static bool get isWeb => true;
}

// Mock File class for web
class File {
  final String path;
  
  File(this.path);
  
  Future<void> writeAsBytes(List<int> bytes) async {
    // No-op for web
    return;
  }
  
  Future<void> writeAsString(String content) async {
    // No-op for web
    return;
  }
  
  String get absolute => path;
  
  // For compatibility with FileImage
  operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is File && other.path == path;
  }
  
  @override
  int get hashCode => path.hashCode;
}

// Mock Directory class for web
class Directory {
  final String path;
  
  Directory(this.path);
  
  String get absolute => path;
}
