import 'dart:io';
import 'dart:developer' as developer;
import 'package:flutter/services.dart';

/// Service for integrating with Apple Notes app on iOS
class AppleNotesService {
  static const _channel = MethodChannel('com.omi.apple_notes');
  
  /// Check if this service is available (iOS only)
  bool get isAvailable => Platform.isIOS;

  /// Share an action item to Apple Notes using native share sheet
  Future<({bool isSuccess, String message})> shareActionItem(String description) async {
    if (!isAvailable) {
      return (
        isSuccess: false,
        message: 'Apple Notes is only available on iOS'
      );
    }

    try {
      final formattedContent = '''
📝 Action Item from Omi
━━━━━━━━━━━━━━━━━
$description

Added: ${DateTime.now().toString().split('.')[0]}
''';

      final result = await _channel.invokeMethod('shareToNotes', {
        'content': formattedContent,
      });

      return result == true
          ? (isSuccess: true, message: 'Opening share sheet...')
          : (isSuccess: false, message: 'Could not open share sheet');
    } on PlatformException catch (e) {
      return (
        isSuccess: false,
        message: 'Error: ${e.message ?? 'Unknown error'}'
      );
    } catch (e) {
      return (
        isSuccess: false,
        message: 'Unexpected error: $e'
      );
    }
  }

  /// Check if Notes app is available
  Future<bool> isNotesAppAvailable() async {
    if (!isAvailable) return false;

    try {
      final result = await _channel.invokeMethod('isNotesAppAvailable');
      return result == true;
    } catch (e) {
      developer.log('Error checking Notes availability: $e',
          name: 'AppleNotesService');
      return false;
    }
  }
}