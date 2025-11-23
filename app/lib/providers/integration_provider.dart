import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/pages/settings/integrations_page.dart';

class IntegrationProvider extends ChangeNotifier {
  Map<String, bool> _integrations = {};

  Map<String, bool> get integrations => _integrations;

  Future<void> loadFromBackend() async {
    try {
      final responses = await Future.wait([
        getIntegration('google_calendar'),
        getIntegration('whoop'),
        getIntegration('notion'),
        getIntegration('twitter'),
      ]);

      _integrations['google_calendar'] = responses[0]?.connected ?? false;
      _integrations['whoop'] = responses[1]?.connected ?? false;
      _integrations['notion'] = responses[2]?.connected ?? false;
      _integrations['twitter'] = responses[3]?.connected ?? false;

      notifyListeners();
    } catch (e) {
      debugPrint('Error loading integrations from backend: $e');
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
    }
  }
}
