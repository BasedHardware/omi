import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:friend_private/utils/platform_imports.dart';

class PlatformFile {
  static Future<File?> createFile(String path, List<int> data) async {
    if (kIsWeb) {
      return File(path); // Mock implementation for web
    } else {
      final file = File(path);
      await file.writeAsBytes(data);
      return file;
    }
  }
}
