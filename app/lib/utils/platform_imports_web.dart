// Platform-specific imports for web platform
import 'dart:html' as html;
import 'dart:typed_data' as typed_data;
import 'package:flutter/foundation.dart' show kIsWeb;

// Re-export dart:typed_data for compatibility
export 'dart:typed_data';

// Mock classes for web platform
class File {
  final String path;
  
  File(this.path);
  
  Future<File> writeAsBytes(List<int> bytes) async {
    // Web implementation (no-op)
    return this;
  }
  
  Future<File> writeAsString(String contents) async {
    // Web implementation (no-op)
    return this;
  }
  
  Future<bool> exists() async {
    // Web implementation
    return false;
  }
  
  // Sync methods needed for web compatibility
  bool existsSync() {
    // Web implementation
    return false;
  }
  
  void deleteSync() {
    // Web implementation (no-op)
  }
  
  String get path => this.path;
  
  String get absolute => this.path;
  
  // For compatibility with dart:io File
  File get absolute => this;
}

class Directory extends FileSystemEntity {
  Directory(String path) : super(path);
  
  Future<bool> exists() async {
    // Web implementation
    return false;
  }
  
  bool existsSync() {
    // Web implementation
    return false;
  }
  
  List<FileSystemEntity> listSync({bool recursive = false, bool followLinks = true}) {
    // Web implementation
    return [];
  }
  
  Stream<FileSystemEntity> list({bool recursive = false, bool followLinks = true}) {
    // Web implementation
    return Stream.fromIterable([]);
  }
}

// Base class for File and Directory
class FileSystemEntity {
  final String path;
  
  FileSystemEntity(this.path);
  
  Future<bool> exists() async {
    return false;
  }
  
  Future<FileSystemEntity> delete() async {
    return this;
  }
  
  Future<int> length() async {
    return 0;
  }
}

// Mock Platform class for web
class Platform {
  static bool get isIOS => false;
  static bool get isAndroid => false;
  static bool get isMacOS => false;
  static bool get isWindows => false;
  static bool get isLinux => false;
  static bool get isFuchsia => false;
}

// We'll use the real Uint8List from dart:typed_data instead of mocking it
// This avoids type compatibility issues

// We don't need to mock path_provider functions here
// The actual implementations will be used from the path_provider package
// We'll just add conditional checks in the code that uses these functions
