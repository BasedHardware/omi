import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class FloatingChatService {
  static const MethodChannel _chatChannel = MethodChannel('com.omi/floating_chat');

  static final StreamController<Map<String, dynamic>> _messageController = StreamController.broadcast();

  static Stream<Map<String, dynamic>> get onMessageReceived => _messageController.stream;

  static void init() {
    _chatChannel.setMethodCallHandler(_handleMethodCall);
  }

  static Future<dynamic> _handleMethodCall(MethodCall call) async {
    debugPrint("adasd");
    switch (call.method) {
      case 'userMessage':
        if (call.arguments is Map) {
          final args = Map<String, dynamic>.from(call.arguments);
          _messageController.add(args);
        }
        break;
      case 'requestHistory':
        if (call.arguments is Map) {
          final args = Map<String, dynamic>.from(call.arguments);
          // Add a type to distinguish from a user message
          _messageController.add(args..['type'] = 'requestHistory');
        }
        break;
      default:
        print('FloatingChatService: Unknown method call ${call.method}');
    }
  }

  static Future<void> _invokeMethodWithRetry(MethodChannel channel, String method, [dynamic arguments]) async {
    int attempts = 0;
    const maxAttempts = 3;
    const delay = Duration(milliseconds: 200);

    while (attempts < maxAttempts) {
      try {
        await channel.invokeMethod(method, arguments);
        return; // Success
      } on PlatformException catch (e) {
        attempts++;
        print("Failed to invoke '$method' (attempt $attempts/$maxAttempts): '${e.message}'.");
        if (attempts >= maxAttempts) {
          print("Max retries reached for '$method'. Giving up.");
          rethrow;
        }
        await Future.delayed(delay * attempts); // Linear backoff
      }
    }
  }

  static Future<void> sendAIResponse(Map<String, dynamic> message) async {
    try {
      await _invokeMethodWithRetry(_chatChannel, 'aiResponse', message);
    } on PlatformException catch (e) {
      print("Failed to send AI response to Swift after retries: '${e.message}'.");
    }
  }

  static Future<void> sendChatHistory(Map<String, dynamic> historyData) async {
    try {
      await _invokeMethodWithRetry(_chatChannel, 'chatHistory', historyData);
    } on PlatformException catch (e) {
      print("Failed to send chat history to Swift after retries: '${e.message}'.");
    }
  }

  static Future<void> showChatWindow(String id) async {
    try {
      await _invokeMethodWithRetry(_chatChannel, 'showChatWindow', {'id': id});
    } on PlatformException catch (e) {
      print("Failed to show chat window after retries: '${e.message}'.");
    }
  }

  static Future<void> hideChatWindow(String id) async {
    try {
      await _invokeMethodWithRetry(_chatChannel, 'hideChatWindow', {'id': id});
    } on PlatformException catch (e) {
      print("Failed to hide chat window after retries: '${e.message}'.");
    }
  }
}
