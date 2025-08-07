import 'dart:convert';
import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/auth.dart' as backend_auth;

/// Bridge class to sync authentication and app state with macOS overlay
class MacOSOverlayBridge {
  static const _userTokenKey = 'flutter.authToken';
  static const _userIdKey = 'flutter.userId';
  static const _selectedAppKey = 'flutter.selectedChatAppId';
  static const _messagesKey = 'flutter_to_swift_messages';
  static const _tokenRefreshRequestKey = 'swift_overlay_needs_token_refresh';
  static const _tokenTimestampKey = 'flutter.authTokenTimestamp';
  static const _chatExpansionRequestKey = 'swift_overlay_open_full_chat';
  
  // Platform channel for UserDefaults communication
  static const _platformChannel = MethodChannel('overlayPlatform');
  
  static Timer? _refreshCheckTimer;
  
  /// Sync current authentication state to macOS overlay
  static Future<void> syncAuthToOverlay() async {
    try {
      final prefs = SharedPreferencesUtil();
      
      // Sync auth token
      final authToken = prefs.authToken;
      if (authToken.isNotEmpty) {
        await _setUserDefault(_userTokenKey, authToken);
        await _setUserDefault(_tokenTimestampKey, DateTime.now().millisecondsSinceEpoch.toDouble());
        debugPrint('✅ Synced auth token to overlay');
      }
      
      // Sync user ID (from Firebase)
      final userId = SharedPreferencesUtil().uid;
      if (userId.isNotEmpty) {
        await _setUserDefault(_userIdKey, userId);
        debugPrint('✅ Synced user ID to overlay: $userId');
      }
      
      debugPrint('📤 Authentication sync to macOS overlay completed');
    } catch (e) {
      debugPrint('❌ Failed to sync auth to overlay: $e');
    }
  }
  
  /// Sync selected chat app to overlay
  static Future<void> syncSelectedApp(String? appId) async {
    try {
      await _setUserDefault(_selectedAppKey, appId ?? 'no_selected');
      debugPrint('✅ Synced selected app to overlay: ${appId ?? "none"}');
    } catch (e) {
      debugPrint('❌ Failed to sync selected app to overlay: $e');
    }
  }
  
  /// Sync messages to overlay (for continuity)
  static Future<void> syncMessagesToOverlay(List<Map<String, dynamic>> messages) async {
    try {
      // Convert messages to sync format
      final syncMessages = messages.take(20).map((msg) => {
        'id': msg['id'] ?? '',
        'content': msg['text'] ?? '',
        'isUser': msg['sender'] == 'human',
        'timestamp': msg['created_at'] ?? DateTime.now().toIso8601String(),
        'source': 'flutter_app'
      }).toList();
      
      final jsonString = jsonEncode(syncMessages);
      await _setUserDefault(_messagesKey, jsonString);
      
      debugPrint('✅ Synced ${syncMessages.length} messages to overlay');
    } catch (e) {
      debugPrint('❌ Failed to sync messages to overlay: $e');
    }
  }
  
  /// Get messages from overlay
  static Future<List<Map<String, dynamic>>> getMessagesFromOverlay() async {
    try {
      final data = await _getUserDefault('swift_overlay_messages');
      if (data != null && data is String) {
        final List<dynamic> decoded = jsonDecode(data);
        return decoded.cast<Map<String, dynamic>>();
      }
    } catch (e) {
      debugPrint('❌ Failed to get messages from overlay: $e');
    }
    return [];
  }
  
  /// Check if overlay is authenticated
  static Future<bool> isOverlayAuthenticated() async {
    try {
      final status = await _getUserDefault('swift_overlay_auth_status');
      return status == true;
    } catch (e) {
      debugPrint('❌ Failed to check overlay auth status: $e');
      return false;
    }
  }
  
  /// Check for chat expansion request from Swift overlay
  static Future<bool> checkForChatExpansionRequest() async {
    try {
      final shouldExpand = await _getUserDefault(_chatExpansionRequestKey);
      
      if (shouldExpand == true) {
        // Reset the flag to prevent repeated triggers
        await _setUserDefault(_chatExpansionRequestKey, false);
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('❌ Failed to check chat expansion request: $e');
      return false;
    }
  }
  
  /// Initialize overlay with current app state
  static Future<void> initializeOverlay() async {
    debugPrint('🚀 Initializing macOS overlay...');
    
    await syncAuthToOverlay();
    
    // Sync current selected app if available
    final selectedApp = SharedPreferencesUtil().selectedChatAppId;
    await syncSelectedApp(selectedApp);
    
    // Start listening for token refresh requests from Swift overlay
    _startTokenRefreshListener();
    
    debugPrint('✅ macOS overlay initialization completed');
  }
  
  /// Start listening for token refresh requests from Swift overlay
  static void _startTokenRefreshListener() {
    _refreshCheckTimer?.cancel();
    _refreshCheckTimer = Timer.periodic(const Duration(seconds: 1), (timer) async {
      try {
        final needsRefresh = await _getUserDefault(_tokenRefreshRequestKey);
        if (needsRefresh == true) {
          debugPrint('🔄 Swift overlay requested token refresh');
          
          // Clear the request flag
          await _setUserDefault(_tokenRefreshRequestKey, false);
          
          // Get fresh token
          final freshToken = await backend_auth.getIdToken();
          if (freshToken != null && freshToken.isNotEmpty) {
            // Update local preferences
            SharedPreferencesUtil().authToken = freshToken;
            
            // Sync fresh token to overlay
            await syncAuthToOverlay();
            debugPrint('✅ Fresh token synced to overlay');
          } else {
            debugPrint('❌ Failed to get fresh token for overlay');
          }
        }
      } catch (e) {
        debugPrint('❌ Error in token refresh listener: $e');
      }
    });
  }
  
  /// Stop token refresh listener
  static void stopTokenRefreshListener() {
    _refreshCheckTimer?.cancel();
    _refreshCheckTimer = null;
  }
  
  // Platform-specific UserDefaults access
  static Future<void> _setUserDefault(String key, dynamic value) async {
    try {
      await _platformChannel.invokeMethod('setUserDefault', {
        'key': key,
        'value': value,
      });
    } catch (e) {
      debugPrint('❌ Failed to set UserDefault "$key": $e');
      // Fallback to SharedPreferences for development
      final prefs = SharedPreferencesUtil();
      if (value is String) {
        prefs.saveString(key, value);
      } else if (value is bool) {
        prefs.saveBool(key, value);
      } else if (value is int) {
        prefs.saveInt(key, value);
      } else if (value is double) {
        prefs.saveDouble(key, value);
      }
    }
  }

  static Future<dynamic> _getUserDefault(String key) async {
    try {
      final result = await _platformChannel.invokeMethod('getUserDefault', {'key': key});
      return result;
    } catch (e) {
      debugPrint('❌ Failed to get UserDefault "$key": $e');
      // Fallback to SharedPreferences for development
      try {
        final prefs = SharedPreferencesUtil();
        
        // Try boolean first (for expansion flags)
        try {
          final boolValue = prefs.getBool(key);
          if (boolValue != null) {
            return boolValue;
          }
        } catch (e) {
          // Not a boolean, try string
        }
        
        // Try string next
        final stringValue = prefs.getString(key);
        if (stringValue != null && stringValue.isNotEmpty) {
          // Check if it's a boolean stored as string
          if (stringValue == 'true') return true;
          if (stringValue == 'false') return false;
          return stringValue;
        }
        
        return null;
      } catch (e2) {
        debugPrint('❌ Error reading UserDefault for key $key: $e2');
        return null;
      }
    }
  }
}
