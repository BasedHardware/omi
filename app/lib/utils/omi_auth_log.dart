import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

final class OmiAuthLog {
  static const MethodChannel _channel = MethodChannel('com.omi/auth_log');

  static Future<void> info(String message) async {
    debugPrint('[OmiAuth] $message');
    try {
      await _channel.invokeMethod<void>('log', message);
    } catch (_) {
      // Native logging is diagnostic only. Auth flow must not depend on it.
    }
  }
}
