import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/services/integrations/connection_read.dart';

import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';

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
    this.statusTimeout = const Duration(seconds: 45),
  })  : _fetchStatus = fetchStatus ?? getIntegration,
        _saveStatus = saveStatus ?? saveIntegration,
        _deleteStatus = deleteStatus ?? deleteIntegration,
        _persistPref = persistPref ?? _defaultPersistPref;

  final IntegrationStatusFetcher _fetchStatus;
  final IntegrationSaver _saveStatus;
  final IntegrationDeleter _deleteStatus;
  final IntegrationPrefWriter _persistPref;
  final Duration statusTimeout;
  final Set<String> _statusErrors = {};
  int _readGeneration = 0;
  final _activeReads = <ConnectionRead<IntegrationResponse?>>{};

  final Map<String, bool> _integrations = {};
  bool _isLoading = false;
  bool _hasLoaded = false;
  bool _needsRetry = false;
  int _sessionGeneration = 0;
  Future<void>? _inFlightLoad;

  Map<String, bool> get integrations => _integrations;
  bool get isLoading => _isLoading;
  bool get hasLoaded => _hasLoaded;
  bool get hasLoadError => _statusErrors.isNotEmpty;
  bool hasStatusError(IntegrationApp app) => _statusErrors.contains(app.key);

  static List<String> get trackedAppKeys => IntegrationApp.values.map((app) => app.key).toList(growable: false);

  static Future<void> _defaultPersistPref(String key, bool value) {
    return SharedPreferencesUtil().saveBool(key, value);
  }

  static String prefKeyFor(String appKey) => '${appKey}_connected';

  bool _isCurrent(int generation) => generation == _sessionGeneration;

  Future<void> loadFromBackend({bool forceRefresh = false, bool silent = false}) {
    final existing = _inFlightLoad;
    if (existing != null && !forceRefresh) return existing;
    late final Future<void> started;
    started = _loadFromBackendBody(++_readGeneration, silent: silent).whenComplete(() {
      if (identical(_inFlightLoad, started)) _inFlightLoad = null;
    });
    _inFlightLoad = started;
    return started;
  }

  Future<void> _loadFromBackendBody(int readGeneration, {required bool silent}) async {
    final generation = _sessionGeneration;
    bool isCurrent() => _isCurrent(generation) && readGeneration == _readGeneration;
    final syncAttempt = ProductTelemetry.instance.start(
      ProductJourney.integrationSync,
      surface: ProductSurface.integration,
    );
    var syncCompleted = false;
    void completeSync(ProductOutcome outcome, {ProductFailure failure = ProductFailure.none}) {
      if (syncCompleted) return;
      syncCompleted = true;
      syncAttempt.complete(outcome, failure: failure);
    }

    if (!silent) {
      _isLoading = true;
      notifyListeners();
    }

    try {
      final keys = trackedAppKeys;
      // A malformed or unresponsive service must not strand all other rows.
      final responses = await Future.wait(keys.map((key) async {
        try {
          final read = ConnectionRead(() => _fetchStatus(key), statusTimeout);
          _activeReads.add(read);
          try {
            final response = await read.future;
            return response?.appKey == key ? response : null;
          } finally {
            _activeReads.remove(read);
          }
        } catch (_) {
          return null;
        }
      }));
      if (!isCurrent()) {
        completeSync(ProductOutcome.superseded);
        return;
      }

      var allFetched = true;
      for (var i = 0; i < keys.length; i++) {
        final key = keys[i];
        final response = responses[i];
        if (response == null) {
          allFetched = false;
          _statusErrors.add(key);
          _integrations.putIfAbsent(key, () => SharedPreferencesUtil().getBool(prefKeyFor(key)));
          continue;
        }
        _statusErrors.remove(key);
        _integrations[key] = response.connected;
        await _persistPref(prefKeyFor(key), response.connected);
        if (!isCurrent()) {
          completeSync(ProductOutcome.superseded);
          return;
        }
      }

      if (!isCurrent()) {
        completeSync(ProductOutcome.superseded);
        return;
      }
      _hasLoaded = true;
      _needsRetry = !allFetched;
      completeSync(
        allFetched ? ProductOutcome.success : ProductOutcome.failure,
        failure: allFetched ? ProductFailure.none : ProductFailure.network,
      );
    } catch (e) {
      if (!isCurrent()) {
        completeSync(ProductOutcome.superseded);
        return;
      }
      completeSync(ProductOutcome.failure, failure: ProductFailure.network);
      _needsRetry = true;
      _statusErrors.addAll(trackedAppKeys);
      Logger.debug('Error loading integration statuses');
    } finally {
      if (isCurrent()) {
        _isLoading = false;
        _hasLoaded = true;
        notifyListeners();
      }
    }
  }

  Future<void> ensureLoaded() async {
    if (_hasLoaded && !_needsRetry) return;
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
    _readGeneration++;
    for (final read in _activeReads) {
      read.cancel();
    }
    _activeReads.clear();
    _statusErrors.clear();
    _inFlightLoad = null;
    _integrations.clear();
    _isLoading = false;
    _hasLoaded = false;
    _needsRetry = false;
    for (final key in trackedAppKeys) {
      _persistPref(prefKeyFor(key), false);
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _sessionGeneration++;
    _readGeneration++;
    for (final read in _activeReads) {
      read.cancel();
    }
    _activeReads.clear();
    super.dispose();
  }
}
