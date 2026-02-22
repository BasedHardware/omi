import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class EnvironmentDetector {
  static const _channel = MethodChannel('com.omi/environment');

  static Future<bool> isTestFlight() async {
    if (!Platform.isIOS) return false;
    if (!kReleaseMode) return false;
    try {
      final bool result = await _channel.invokeMethod('isTestFlight');
      return result;
    } catch (e) {
      debugPrint('EnvironmentDetector: Failed to check TestFlight: $e');
      return false;
    }
  }
}
