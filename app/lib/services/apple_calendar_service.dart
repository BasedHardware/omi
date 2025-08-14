import 'package:flutter/services.dart';

class AppleCalendarService {
  static const _channel = MethodChannel('com.omi.apple_calendar');

  /// Creates an event in Apple Calendar from an action item
  Future<({bool isSuccess, String message})> createEvent(String description) async {
    try {
      // Format the content for Calendar
      final formattedContent = '''
Action Item: $description

Created: ${DateTime.now().toLocal()}
Source: OMI App
''';

      final result = await _channel.invokeMethod('createEvent', {
        'title': description,
        'notes': formattedContent,
      });

      if (result is Map) {
        return (
          isSuccess: result['success'] as bool? ?? false,
          message: result['message'] as String? ?? 'Unknown response'
        );
      }

      return (isSuccess: false, message: 'Invalid response format');
    } on PlatformException catch (e) {
      return (isSuccess: false, message: e.message ?? 'Failed to create calendar event');
    } catch (e) {
      return (isSuccess: false, message: 'Unexpected error: $e');
    }
  }

  /// Checks if Apple Calendar is available on the device
  Future<bool> isAvailable() async {
    try {
      final result = await _channel.invokeMethod('checkAvailability');
      return result as bool? ?? false;
    } catch (e) {
      return false;
    }
  }
}