import 'dart:convert';
import 'dart:async';
import 'package:flutter/foundation.dart';
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
      
      // Sync device ID if available - placeholder for now
      // final deviceId = prefs.deviceId; // Not available in current implementation
      // if (deviceId.isNotEmpty) {
      //   await _setUserDefault(_deviceIdKey, deviceId);
      //   debugPrint('✅ Synced device ID to overlay');
      // }
      
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
    // In a real implementation, this would use platform channels
    // For now, we'll use a simple approach via SharedPreferences
    final prefs = SharedPreferencesUtil();
    if (value is String) {
      prefs.setString(key, value);
    } else if (value is bool) {
      prefs.setBool(key, value);
    } else if (value is int) {
      prefs.setInt(key, value);
    } else if (value is double) {
      prefs.setDouble(key, value);
    }
  }
  
  static Future<dynamic> _getUserDefault(String key) async {
    // In a real implementation, this would use platform channels
    final prefs = SharedPreferencesUtil();
    return prefs.getString(key);
  }
}

/// Extension methods for easier access
extension SharedPreferencesUtilExtension on SharedPreferencesUtil {
  void setString(String key, String value) {
    // This is a placeholder - in real implementation would need platform channel
    // For now, store in regular SharedPreferences
    debugPrint('Setting $key in UserDefaults: ${value.length > 50 ? value.substring(0, 50) + "..." : value}');
  }
  
  void setBool(String key, bool value) {
    debugPrint('Setting $key in UserDefaults: $value');
  }
  
  void setInt(String key, int value) {
    debugPrint('Setting $key in UserDefaults: $value');
  }
  
  void setDouble(String key, double value) {
    debugPrint('Setting $key in UserDefaults: $value');
  }
}
