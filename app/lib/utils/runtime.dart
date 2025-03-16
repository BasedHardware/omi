import 'package:flutter/foundation.dart';

class SafeInit {
  static void init(VoidCallback function, [VoidCallback? webCallback]) async {
    if (kIsWeb) {
      webCallback?.call();
      return;
    }
    function();
  }

  static T evaluate<T>(T iosValue, T androidValue, [T? webValue]) {
    if (kIsWeb) {
      return webValue ?? androidValue;
    }
    return iosValue;
  }
}
