import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:nooto_v2/apps/app_model.dart';
import 'package:nooto_v2/services/api_client.dart';

/// Owns the Apps marketplace state — the catalog from `/v2/apps` and the
/// user's installed-set from `/v1/apps/enabled`. Install/uninstall update
/// the local set optimistically and roll back on backend error.
class AppsProvider extends ChangeNotifier {
  AppsProvider({required ApiClient client}) : _client = client;

  final ApiClient _client;

  List<AppGroup> _groups = const [];
  Set<String> _enabledIds = const {};
  bool _loading = false;
  bool _hasFetched = false;
  String? _error;
  String? _pendingId; // app currently mid-install/uninstall

  List<AppGroup> get groups => _groups;
  bool get loading => _loading;
  bool get hasFetched => _hasFetched;
  String? get error => _error;
  bool get isEmpty => _groups.isEmpty;

  bool isEnabled(String appId) => _enabledIds.contains(appId);
  bool isPending(String appId) => _pendingId == appId;

  /// Idempotent — safe to call from `initState` of every Apps tab arrival.
  /// Subsequent calls no-op unless [force] is set.
  Future<void> load({bool force = false}) async {
    if (_loading) return;
    if (_hasFetched && !force) return;

    _loading = true;
    _error = null;
    notifyListeners();

    try {
      final results = await Future.wait([
        _client.get('v2/apps?offset=0&limit=20'),
        _client.get('v1/apps/enabled'),
      ]);

      final catalog = jsonDecode(results[0].body) as Map<String, dynamic>;
      final raw = catalog['groups'];
      final parsed = raw is List
          ? raw
              .whereType<Map>()
              .map((m) => AppGroup.fromJson(Map<String, dynamic>.from(m)))
              .where((g) => g.apps.isNotEmpty)
              .toList(growable: false)
          : const <AppGroup>[];

      final enabledRaw = jsonDecode(results[1].body);
      final enabledIds = enabledRaw is List
          ? enabledRaw.map((e) => e.toString()).toSet()
          : <String>{};

      _groups = parsed;
      _enabledIds = enabledIds;
      _hasFetched = true;
    } catch (e, st) {
      debugPrint('[AppsProvider] load failed: $e\n$st');
      _error = e.toString();
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  /// Install the app. Optimistic — flips local enabled state immediately,
  /// rolls back if the backend rejects. Returns true on success.
  Future<bool> install(String appId) async {
    if (_pendingId != null || _enabledIds.contains(appId)) return false;
    _pendingId = appId;
    _enabledIds = {..._enabledIds, appId};
    notifyListeners();
    try {
      final res = await _client.post('v1/apps/enable?app_id=$appId');
      if (res.statusCode < 200 || res.statusCode >= 300) {
        throw Exception('install: HTTP ${res.statusCode}');
      }
      return true;
    } catch (e) {
      debugPrint('[AppsProvider] install($appId) failed: $e');
      _enabledIds = {..._enabledIds}..remove(appId);
      _error = e.toString();
      return false;
    } finally {
      _pendingId = null;
      notifyListeners();
    }
  }

  /// Uninstall the app. Optimistic with rollback, mirrors [install].
  Future<bool> uninstall(String appId) async {
    if (_pendingId != null || !_enabledIds.contains(appId)) return false;
    _pendingId = appId;
    _enabledIds = {..._enabledIds}..remove(appId);
    notifyListeners();
    try {
      final res = await _client.post('v1/apps/disable?app_id=$appId');
      if (res.statusCode < 200 || res.statusCode >= 300) {
        throw Exception('uninstall: HTTP ${res.statusCode}');
      }
      return true;
    } catch (e) {
      debugPrint('[AppsProvider] uninstall($appId) failed: $e');
      _enabledIds = {..._enabledIds, appId};
      _error = e.toString();
      return false;
    } finally {
      _pendingId = null;
      notifyListeners();
    }
  }
}
