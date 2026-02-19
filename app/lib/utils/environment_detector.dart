import 'dart:io';

import 'package:flutter/services.dart';

class EnvironmentDetector {
  static const _channel = MethodChannel('com.omi/environment');

  static Future<bool> isTestFlight() async {
    if (!Platform.isIOS) return false;
    try {
      final result = await _channel.invokeMethod<bool>('isTestFlight');
      return result ?? false;
    } on PlatformException {
      return false;
    }
  }
}
