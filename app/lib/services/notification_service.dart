import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:friend_private/backend/http/api/notifications.dart';
import 'package:friend_private/backend/preferences.dart';

class NotificationService {
  NotificationService._();
  static NotificationService instance = NotificationService._();
  MethodChannel platform = const MethodChannel('com.friend.ios/notifyOnKill');
  final FirebaseMessaging _firebaseMessaging = FirebaseMessaging.instance;

  Future<void> initialize() async {
    await register();
    registerNotification();
  }

  Future<void> register() async {
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

  Future<String> getTimeZone() async {
    final String currentTimeZone = await FlutterTimezone.getLocalTimezone();
    return currentTimeZone;
  }

  Future<void> saveToken(String? token) async {
    if (token == null) return;
    final userId = SharedPreferencesUtil().uid;
    String timeZone = await getTimeZone();
    await saveTokenToBackend(
      userId: userId,
      token: token,
      timeZone: timeZone,
    );
  }

  void registerNotification() async {
    String? token = await _firebaseMessaging.getToken();
    await saveToken(token);
    _firebaseMessaging.onTokenRefresh.listen(saveToken);
  }
}
