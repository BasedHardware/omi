import 'package:flutter/material.dart';
import 'package:friend_private/providers/web_auth_provider.dart';
import 'package:friend_private/services/web_notification_service.dart';
import 'package:friend_private/services/web_service_manager.dart';
import 'package:friend_private/utils/platform_utils.dart';

/// Utility class for web-specific initialization
class WebInitializer {
  /// Initialize all web-specific services and utilities
  static Future<bool> initializeWeb() async {
    debugPrint('Initializing web platform services');
    
    // Initialize web service manager
    WebServiceManager.init();
    
    // Initialize web notification service
    await WebNotificationService.instance.initialize();
    
    // Start web services
    await WebServiceManager.instance().start();
    
    // Check authentication status
    final authProvider = WebAuthenticationProvider();
    final isAuth = authProvider.isSignedIn();
    
    debugPrint('Web initialization complete. Auth status: $isAuth');
    return isAuth;
  }
  
  /// Check if the current platform is web
  static bool isWebPlatform() {
    return PlatformUtils.isWeb;
  }
}
