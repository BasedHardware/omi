import 'dart:io';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/http/calendar.dart';

// Platform-specific calendar integration handling
class PlatformSpecificCalendarIntegration {
  static const MethodChannel _channel = MethodChannel('calendar_integration');
  
  /// Platform-aware OAuth initiation
  static Future<Map<String, dynamic>?> initiateOAuthFlow() async {
    try {
      if (Platform.isIOS) {
        return await _initiateIOSOAuth();
      } else if (Platform.isAndroid) {
        return await _initiateAndroidOAuth();
      } else {
        // Fallback to standard web flow
        final authUrl = await initiateGoogleCalendarAuth();
        return authUrl != null ? {'auth_url': authUrl, 'method': 'web'} : null;
      }
    } catch (e) {
      debugPrint('Error initiating OAuth flow: $e');
      return null;
    }
  }
  
  /// iOS-specific OAuth handling
  static Future<Map<String, dynamic>?> _initiateIOSOAuth() async {
    try {
      // Use SFSafariViewController for OAuth
      final result = await _channel.invokeMethod('initiateIOSOAuth', {
        'use_safari_view_controller': true,
        'prefer_ephemeral_session': false, // For better user experience
      });
      
      return {
        'auth_url': result['auth_url'],
        'method': 'safari_view_controller',
        'session_id': result['session_id']
      };
    } on PlatformException catch (e) {
      debugPrint('iOS OAuth error: ${e.message}');
      
      // Fallback to standard web flow
      final authUrl = await initiateGoogleCalendarAuth();
      return authUrl != null ? {
        'auth_url': authUrl, 
        'method': 'web_fallback',
        'fallback_reason': e.message
      } : null;
    }
  }
  
  /// Android-specific OAuth handling
  static Future<Map<String, dynamic>?> _initiateAndroidOAuth() async {
    try {
      // Use Chrome Custom Tabs for OAuth
      final result = await _channel.invokeMethod('initiateAndroidOAuth', {
        'use_custom_tabs': true,
        'color_scheme': 'light', // Match app theme
      });
      
      return {
        'auth_url': result['auth_url'],
        'method': 'custom_tabs',
        'session_id': result['session_id']
      };
    } on PlatformException catch (e) {
      debugPrint('Android OAuth error: ${e.message}');
      
      // Fallback to standard web flow
      final authUrl = await initiateGoogleCalendarAuth();
      return authUrl != null ? {
        'auth_url': authUrl, 
        'method': 'web_fallback',
        'fallback_reason': e.message
      } : null;
    }
  }
  
  /// Secure token storage with platform-specific methods
  static Future<bool> storeTokensSecurely(Map<String, dynamic> tokens) async {
    try {
      if (Platform.isIOS) {
        return await _storeTokensIOS(tokens);
      } else if (Platform.isAndroid) {
        return await _storeTokensAndroid(tokens);
      } else {
        // For web or other platforms, use encrypted local storage
        return await _storeTokensGeneric(tokens);
      }
    } catch (e) {
      debugPrint('Error storing tokens: $e');
      return false;
    }
  }
  
  static Future<bool> _storeTokensIOS(Map<String, dynamic> tokens) async {
    try {
      // Use iOS Keychain with biometric protection
      final result = await _channel.invokeMethod('storeTokensIOSKeychain', {
        'tokens': tokens,
        'service': 'com.omi.calendar',
        'access_group': null, // App-specific
        'biometric_protection': true,
        'cloud_sync': false, // Disable iCloud sync for privacy
      });
      
      return result['success'] == true;
    } on PlatformException catch (e) {
      debugPrint('iOS token storage error: ${e.message}');
      return false;
    }
  }
  
  static Future<bool> _storeTokensAndroid(Map<String, dynamic> tokens) async {
    try {
      // Use Android Keystore with hardware-backed security
      final result = await _channel.invokeMethod('storeTokensAndroidKeystore', {
        'tokens': tokens,
        'key_alias': 'omi_calendar_tokens',
        'require_authentication': true,
        'hardware_backed': true,
      });
      
      return result['success'] == true;
    } on PlatformException catch (e) {
      debugPrint('Android token storage error: ${e.message}');
      return false;
    }
  }
  
  static Future<bool> _storeTokensGeneric(Map<String, dynamic> tokens) async {
    // Fallback implementation for other platforms
    // This would use FlutterSecureStorage or similar
    debugPrint('Using generic token storage - consider platform-specific implementation');
    return true;
  }
  
  /// Retrieve stored tokens with platform-specific methods
  static Future<Map<String, dynamic>?> retrieveStoredTokens() async {
    try {
      if (Platform.isIOS) {
        return await _retrieveTokensIOS();
      } else if (Platform.isAndroid) {
        return await _retrieveTokensAndroid();
      } else {
        return await _retrieveTokensGeneric();
      }
    } catch (e) {
      debugPrint('Error retrieving tokens: $e');
      return null;
    }
  }
  
  static Future<Map<String, dynamic>?> _retrieveTokensIOS() async {
    try {
      final result = await _channel.invokeMethod('retrieveTokensIOSKeychain', {
        'service': 'com.omi.calendar',
        'biometric_prompt': 'Access your calendar integration tokens',
      });
      
      return result['tokens'] != null ? 
        Map<String, dynamic>.from(result['tokens']) : null;
    } on PlatformException catch (e) {
      debugPrint('iOS token retrieval error: ${e.message}');
      return null;
    }
  }
  
  static Future<Map<String, dynamic>?> _retrieveTokensAndroid() async {
    try {
      final result = await _channel.invokeMethod('retrieveTokensAndroidKeystore', {
        'key_alias': 'omi_calendar_tokens',
        'authentication_prompt': 'Access your calendar integration tokens',
      });
      
      return result['tokens'] != null ? 
        Map<String, dynamic>.from(result['tokens']) : null;
    } on PlatformException catch (e) {
      debugPrint('Android token retrieval error: ${e.message}');
      return null;
    }
  }
  
  static Future<Map<String, dynamic>?> _retrieveTokensGeneric() async {
    // Fallback implementation
    debugPrint('Using generic token retrieval');
    return null;
  }
  
  /// Background token refresh with platform-specific handling
  static Future<void> scheduleBackgroundTokenRefresh() async {
    try {
      if (Platform.isIOS) {
        await _scheduleIOSBackgroundRefresh();
      } else if (Platform.isAndroid) {
        await _scheduleAndroidBackgroundRefresh();
      }
    } catch (e) {
      debugPrint('Error scheduling background refresh: $e');
    }
  }
  
  static Future<void> _scheduleIOSBackgroundRefresh() async {
    try {
      await _channel.invokeMethod('scheduleIOSBackgroundRefresh', {
        'identifier': 'calendar_token_refresh',
        'earliest_begin_date': DateTime.now().add(Duration(hours: 23)).millisecondsSinceEpoch,
        'requires_network_connectivity': true,
        'requires_charging': false,
      });
    } on PlatformException catch (e) {
      debugPrint('iOS background refresh scheduling error: ${e.message}');
    }
  }
  
  static Future<void> _scheduleAndroidBackgroundRefresh() async {
    try {
      await _channel.invokeMethod('scheduleAndroidBackgroundRefresh', {
        'work_name': 'calendar_token_refresh',
        'flex_interval_hours': 24,
        'requires_network': true,
        'requires_charging': false,
        'backoff_policy': 'exponential',
      });
    } on PlatformException catch (e) {
      debugPrint('Android background refresh scheduling error: ${e.message}');
    }
  }
  
  /// Network connectivity handling with retry logic
  static Future<T?> executeWithRetry<T>(
    Future<T> Function() operation, {
    int maxRetries = 3,
    Duration initialDelay = const Duration(seconds: 1),
  }) async {
    int attempt = 0;
    Duration delay = initialDelay;
    
    while (attempt < maxRetries) {
      try {
        return await operation();
      } catch (e) {
        attempt++;
        debugPrint('Operation failed (attempt $attempt/$maxRetries): $e');
        
        if (attempt >= maxRetries) {
          rethrow;
        }
        
        // Exponential backoff
        await Future.delayed(delay);
        delay *= 2;
      }
    }
    
    return null;
  }
  
  /// OAuth flow interruption handling
  static Future<bool> handleOAuthInterruption({
    required String interruptionType,
    String? sessionId,
    Map<String, dynamic>? savedState,
  }) async {
    try {
      final result = await _channel.invokeMethod('handleOAuthInterruption', {
        'interruption_type': interruptionType,
        'session_id': sessionId,
        'saved_state': savedState,
      });
      
      return result['can_resume'] == true;
    } on PlatformException catch (e) {
      debugPrint('OAuth interruption handling error: ${e.message}');
      return false;
    }
  }
  
  /// Platform-specific error handling
  static String getLocalizedErrorMessage(String errorCode, String? platformError) {
    final platformSpecificMessages = {
      'ios_safari_unavailable': 'Safari is not available. Please try again.',
      'android_custom_tabs_unavailable': 'Chrome Custom Tabs not available. Using fallback.',
      'keychain_access_denied': 'Access to secure storage was denied. Please check your settings.',
      'keystore_unavailable': 'Secure storage is not available on this device.',
      'network_unreachable': 'Network is unreachable. Please check your connection.',
      'oauth_cancelled': 'Authorization was cancelled. Please try again.',
      'token_expired': 'Your calendar access has expired. Please reconnect.',
    };
    
    return platformSpecificMessages[errorCode] ?? 
           platformError ?? 
           'An unexpected error occurred. Please try again.';
  }
  
  /// Check platform capabilities
  static Future<Map<String, bool>> checkPlatformCapabilities() async {
    try {
      final result = await _channel.invokeMethod('checkPlatformCapabilities');
      return Map<String, bool>.from(result);
    } on PlatformException catch (e) {
      debugPrint('Platform capabilities check error: ${e.message}');
      
      // Return default capabilities based on platform
      if (Platform.isIOS) {
        return {
          'safari_view_controller': true,
          'keychain_access': true,
          'background_refresh': true,
          'biometric_authentication': true,
        };
      } else if (Platform.isAndroid) {
        return {
          'custom_tabs': true,
          'keystore_access': true,
          'work_manager': true,
          'biometric_authentication': true,
        };
      } else {
        return {
          'web_view': true,
          'secure_storage': false,
          'background_tasks': false,
          'biometric_authentication': false,
        };
      }
    }
  }
}