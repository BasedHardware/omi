import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class NotifyOnKill {
  static const platform = MethodChannel('com.friend.ios/notifyOnKill');

  static Future<void> register() async {
    try {
      await platform.invokeMethod(
        'setNotificationOnKillService',
        {
          'title': "Application killed!",
          'description':
              "Restart Friend to continue syncing with your wearable",
        },
      );
    } catch (e) {
      debugPrint('NotifOnKill error: $e');
    }
  }
}
