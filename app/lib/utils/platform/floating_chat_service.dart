import 'package:flutter/services.dart';

class FloatingChatService {
  static const MethodChannel _channel = MethodChannel('com.omi/floating_chat');

  static Future<void> showChatWindow() async {
    try {
      await _channel.invokeMethod('showChatWindow');
    } on PlatformException catch (e) {
      print("Failed to show chat window: '${e.message}'.");
    }
  }

  static Future<void> hideChatWindow() async {
    try {
      await _channel.invokeMethod('hideChatWindow');
    } on PlatformException catch (e) {
      print("Failed to hide chat window: '${e.message}'.");
    }
  }

  static Future<void> showButton() async {
    try {
      await _channel.invokeMethod('showButton');
    } on PlatformException catch (e) {
      print("Failed to show button: '${e.message}'.");
    }
  }

  static Future<void> hideButton() async {
    try {
      await _channel.invokeMethod('hideButton');
    } on PlatformException catch (e) {
      print("Failed to hide button: '${e.message}'.");
    }
  }

  static Future<void> resetButtonPosition() async {
    try {
      await _channel.invokeMethod('resetButtonPosition');
    } on PlatformException catch (e) {
      print("Failed to reset button position: '${e.message}'.");
    }
  }

  static Future<void> resetAllPositions() async {
    try {
      await _channel.invokeMethod('resetAllPositions');
    } on PlatformException catch (e) {
      print("Failed to reset all positions: '${e.message}'.");
    }
  }
}
