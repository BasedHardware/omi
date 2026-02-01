import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/utils/logger.dart';

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
      ]);

      _integrations['google_calendar'] = responses[0]?.connected ?? false;
      _integrations['gmail'] = false;

      // Sync SharedPreferences for backward compatibility with services
      // This ensures services that read from SharedPreferences stay in sync
      await SharedPreferencesUtil().saveBool('google_calendar_connected', _integrations['google_calendar'] ?? false);
      await SharedPreferencesUtil().saveBool('gmail_connected', _integrations['gmail'] ?? false);

      _hasLoaded = true;
    } catch (e) {
      Logger.debug('Error loading integrations from backend: $e');
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
      Logger.debug('Error saving integration: $e');
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
      Logger.debug('Error deleting integration: $e');
      return false;
    }
  }

  bool isAppConnected(IntegrationApp app) {
    switch (app) {
      case IntegrationApp.googleCalendar:
        return _integrations['google_calendar'] ?? false;
      case IntegrationApp.appleHealth:
        return _integrations['apple_health'] ?? false;
      case IntegrationApp.gmail:
        return _integrations['gmail'] ?? false;
    }
  }
}
