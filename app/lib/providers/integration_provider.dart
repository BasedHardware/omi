import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/utils/logger.dart';

typedef IntegrationStatusFetcher = Future<IntegrationResponse?> Function(String appKey);
typedef IntegrationSaver = Future<bool> Function(String appKey, Map<String, dynamic> details);
typedef IntegrationDeleter = Future<bool> Function(String appKey);
typedef IntegrationPrefWriter = Future<void> Function(String key, bool value);

class IntegrationProvider extends ChangeNotifier {
  IntegrationProvider({
    IntegrationStatusFetcher? fetchStatus,
    IntegrationSaver? saveStatus,
    IntegrationDeleter? deleteStatus,
    IntegrationPrefWriter? persistPref,
  })  : _fetchStatus = fetchStatus ?? getIntegration,
        _saveStatus = saveStatus ?? saveIntegration,
        _deleteStatus = deleteStatus ?? deleteIntegration,
        _persistPref = persistPref ?? _defaultPersistPref;

  final IntegrationStatusFetcher _fetchStatus;
  final IntegrationSaver _saveStatus;
  final IntegrationDeleter _deleteStatus;
  final IntegrationPrefWriter _persistPref;

  final Map<String, bool> _integrations = {};
  bool _isLoading = false;
  bool _hasLoaded = false;
  int _sessionGeneration = 0;
  Future<void>? _inFlightLoad;

  Map<String, bool> get integrations => _integrations;
  bool get isLoading => _isLoading;
  bool get hasLoaded => _hasLoaded;

  static List<String> get trackedAppKeys => IntegrationApp.values.map((app) => app.key).toList(growable: false);

  static Future<void> _defaultPersistPref(String key, bool value) {
    return SharedPreferencesUtil().saveBool(key, value);
  }

  static String prefKeyFor(String appKey) => '${appKey}_connected';

  bool _isCurrent(int generation) => generation == _sessionGeneration;

  Future<void> loadFromBackend() {
    final existing = _inFlightLoad;
    if (existing != null) return existing;
    late final Future<void> started;
    started = _loadFromBackendBody().whenComplete(() {
      if (identical(_inFlightLoad, started)) _inFlightLoad = null;
    });
    _inFlightLoad = started;
    return started;
  }

  Future<void> _loadFromBackendBody() async {
    final generation = _sessionGeneration;
    _isLoading = true;
    notifyListeners();

    try {
      final keys = trackedAppKeys;
      final responses = await Future.wait(keys.map(_fetchStatus));
      if (!_isCurrent(generation)) return;

      for (var i = 0; i < keys.length; i++) {
        final connected = responses[i]?.connected ?? false;
        _integrations[keys[i]] = connected;
        await _persistPref(prefKeyFor(keys[i]), connected);
        if (!_isCurrent(generation)) return;
      }

      if (!_isCurrent(generation)) return;
      _hasLoaded = true;
    } catch (e) {
      if (!_isCurrent(generation)) return;
      Logger.debug('Error loading integrations from backend: $e');
    } finally {
      if (_isCurrent(generation)) {
        _isLoading = false;
        notifyListeners();
      }
    }
  }

  Future<void> ensureLoaded() async {
    if (_hasLoaded) return;
    await loadFromBackend();
  }

  Future<bool> saveConnection(String appKey, Map<String, dynamic> details) async {
    final generation = _sessionGeneration;
    try {
      final success = await _saveStatus(appKey, details);
      if (!_isCurrent(generation)) return false;
      if (success) {
        _integrations[appKey] = true;
        await _persistPref(prefKeyFor(appKey), true);
        if (!_isCurrent(generation)) return false;
        notifyListeners();
      }
      return success;
    } catch (e) {
      Logger.debug('Error saving integration: $e');
      return false;
    }
  }

  Future<bool> deleteConnection(String appKey) async {
    final generation = _sessionGeneration;
    try {
      final success = await _deleteStatus(appKey);
      if (!_isCurrent(generation)) return false;
      if (success) {
        _integrations[appKey] = false;
        await _persistPref(prefKeyFor(appKey), false);
        if (!_isCurrent(generation)) return false;
        notifyListeners();
      }
      return success;
    } catch (e) {
      Logger.debug('Error deleting integration: $e');
      return false;
    }
  }

  bool isAppConnected(IntegrationApp app) => _integrations[app.key] ?? false;

  void clearUserData() {
    _sessionGeneration++;
    _inFlightLoad = null;
    _integrations.clear();
    _isLoading = false;
    _hasLoaded = false;
    for (final key in trackedAppKeys) {
      _persistPref(prefKeyFor(key), false);
    }
    notifyListeners();
  }
}
