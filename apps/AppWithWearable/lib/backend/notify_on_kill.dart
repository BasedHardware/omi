import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class NotifyOnKill {
  static const platform = MethodChannel('com.friend.ios/notifyOnKill');

  static Future<void> register() async {
    try {
      await platform.invokeMethod(
        'setNotificationOnKillService',
        {
          'title': "Friend Device Disconnected",
          'description': "Please keep your app opened to continue using your Friend.",
        },
      );
    } catch (e) {
      debugPrint('NotifOnKill error: $e');
    }
  }
}
