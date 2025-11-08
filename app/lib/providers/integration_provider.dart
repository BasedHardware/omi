import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/pages/settings/integrations_page.dart';

class IntegrationProvider extends ChangeNotifier {
  Map<String, bool> _integrations = {};

  Map<String, bool> get integrations => _integrations;

  Future<void> loadFromBackend() async {
    try {
      // Check Google Calendar connection
      final googleCalendarResponse = await getIntegration('google_calendar');
      if (googleCalendarResponse != null) {
        _integrations['google_calendar'] = googleCalendarResponse.connected;
      } else {
        _integrations['google_calendar'] = false;
      }

      // Check Whoop connection
      final whoopResponse = await getIntegration('whoop');
      if (whoopResponse != null) {
        _integrations['whoop'] = whoopResponse.connected;
      } else {
        _integrations['whoop'] = false;
      }

      // Check Notion connection
      final notionResponse = await getIntegration('notion');
      if (notionResponse != null) {
        _integrations['notion'] = notionResponse.connected;
      } else {
        _integrations['notion'] = false;
      }

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
    }
  }
}
