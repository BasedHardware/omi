import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:url_launcher/url_launcher.dart';

class NotionService {
  static const String _appKey = 'notion';
  static const String _prefKey = 'notion_connected';

  bool get isAuthenticated {
    // Check both preference and backend
    return SharedPreferencesUtil().getBool(_prefKey) ?? false;
  }

  Future<void> refreshConnectionStatus() async {
    await checkConnection();
  }

  Future<bool> authenticate() async {
    try {
      final authUrl = await getIntegrationOAuthUrl(_appKey);
      if (authUrl == null) {
        debugPrint('Failed to get Notion OAuth URL');
        return false;
      }

      final uri = Uri.parse(authUrl);
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        // Note: OAuth callback will save connection to Firebase
        // The connection status will be updated when user returns to the app
        return true;
      } else {
        debugPrint('Cannot launch Notion OAuth URL');
        return false;
      }
    } catch (e) {
      debugPrint('Error during Notion authentication: $e');
      return false;
    }
  }

  Future<bool> checkConnection() async {
    try {
      final response = await getIntegration(_appKey);
      final isConnected = response != null && response.connected;
      await SharedPreferencesUtil().saveBool(_prefKey, isConnected);
      return isConnected;
    } catch (e) {
      debugPrint('Error checking Notion connection: $e');
      await SharedPreferencesUtil().saveBool(_prefKey, false);
      return false;
    }
  }

  Future<bool> disconnect() async {
    try {
      final success = await deleteIntegration(_appKey);
      if (success) {
        await SharedPreferencesUtil().saveBool(_prefKey, false);
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('Error disconnecting Notion: $e');
      return false;
    }
  }
}
