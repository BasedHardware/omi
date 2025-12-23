import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/integrations_page.dart';

class IntegrationProvider extends ChangeNotifier {
  final Map<String, bool> _integrations = {};
  bool _isLoading = false;
  bool _hasLoaded = false;

  Map<String, bool> get integrations => _integrations;
  bool get isLoading => _isLoading;
  bool get hasLoaded => _hasLoaded;

  Future<void> loadFromBackend() async {
    _isLoading = true;
    notifyListeners();

    try {
      final responses = await Future.wait([
        getIntegration('google_calendar'),
        getIntegration('whoop'),
        getIntegration('notion'),
        getIntegration('twitter'),
        getIntegration('github'),
      ]);

      _integrations['google_calendar'] = responses[0]?.connected ?? false;
      _integrations['whoop'] = responses[1]?.connected ?? false;
      _integrations['notion'] = responses[2]?.connected ?? false;
      _integrations['twitter'] = responses[3]?.connected ?? false;
      _integrations['github'] = responses[4]?.connected ?? false;

      // Sync SharedPreferences for backward compatibility with services
      // This ensures services that read from SharedPreferences stay in sync
      await SharedPreferencesUtil().saveBool('google_calendar_connected', _integrations['google_calendar'] ?? false);
      await SharedPreferencesUtil().saveBool('whoop_connected', _integrations['whoop'] ?? false);
      await SharedPreferencesUtil().saveBool('notion_connected', _integrations['notion'] ?? false);
      await SharedPreferencesUtil().saveBool('twitter_connected', _integrations['twitter'] ?? false);
      await SharedPreferencesUtil().saveBool('github_connected', _integrations['github'] ?? false);

      _hasLoaded = true;
    } catch (e) {
      debugPrint('Error loading integrations from backend: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> saveConnection(String appKey, Map<String, dynamic> details) async {
    try {
      final success = await saveIntegration(appKey, details);
      if (success) {
        _integrations[appKey] = true;
        notifyListeners();
      }
      return success;
    } catch (e) {
      debugPrint('Error saving integration: $e');
      return false;
    }
  }

  Future<bool> deleteConnection(String appKey) async {
    try {
      final success = await deleteIntegration(appKey);
      if (success) {
        _integrations[appKey] = false;
        notifyListeners();
      }
      return success;
    } catch (e) {
      debugPrint('Error deleting integration: $e');
      return false;
    }
  }

  bool isAppConnected(IntegrationApp app) {
    switch (app) {
      case IntegrationApp.googleCalendar:
        return _integrations['google_calendar'] ?? false;
      case IntegrationApp.whoop:
        return _integrations['whoop'] ?? false;
      case IntegrationApp.notion:
        return _integrations['notion'] ?? false;
      case IntegrationApp.twitter:
        return _integrations['twitter'] ?? false;
      case IntegrationApp.github:
        return _integrations['github'] ?? false;
    }
  }
}
