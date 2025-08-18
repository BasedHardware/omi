import 'package:flutter/services.dart';

class AppleCalendarService {
  static const MethodChannel _channel = MethodChannel('com.omi.apple_calendar');

  static Future<bool> requestPermission() async {
    try {
      final bool result = await _channel.invokeMethod('requestPermission');
      return result;
    } on PlatformException catch (e) {
      print('Error requesting calendar permission: ${e.message}');
      return false;
    }
  }

  static Future<bool> addEvent({
    required String title,
    required String notes,
    DateTime? dueDate,
  }) async {
    try {
      final bool result = await _channel.invokeMethod('addEvent', {
        'title': title,
        'notes': notes,
        'dueDate': dueDate?.millisecondsSinceEpoch,
      });
      return result;
    } on PlatformException catch (e) {
      print('Error adding calendar event: ${e.message}');
      return false;
    }
  }
}