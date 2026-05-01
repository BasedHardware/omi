import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:nooto_v2/apps/app_model.dart';
import 'package:nooto_v2/services/api_client.dart';

/// Owns the Apps tab data — fetches `/v2/apps` once on first arrival and
/// caches the capability groups in memory. Pull-to-refresh and per-app
/// install/uninstall actions land in v1; v0 is read-only browsing.
class AppsProvider extends ChangeNotifier {
  AppsProvider({required ApiClient client}) : _client = client;

  final ApiClient _client;

  List<AppGroup> _groups = const [];
  bool _loading = false;
  bool _hasFetched = false;
  String? _error;

  List<AppGroup> get groups => _groups;
  bool get loading => _loading;
  bool get hasFetched => _hasFetched;
  String? get error => _error;
  bool get isEmpty => _groups.isEmpty;

  /// Idempotent — safe to call from `initState` of every Apps tab arrival.
  /// Subsequent calls no-op unless [force] is set.
  Future<void> load({bool force = false}) async {
    if (_loading) return;
    if (_hasFetched && !force) return;

    _loading = true;
    _error = null;
    notifyListeners();

    try {
      final res = await _client.get('v2/apps?offset=0&limit=20');
      final body = jsonDecode(res.body) as Map<String, dynamic>;
      final raw = body['groups'];
      final parsed = raw is List
          ? raw
              .whereType<Map>()
              .map((m) => AppGroup.fromJson(Map<String, dynamic>.from(m)))
              .where((g) => g.apps.isNotEmpty)
              .toList(growable: false)
          : const <AppGroup>[];
      _groups = parsed;
      _hasFetched = true;
    } catch (e, st) {
      debugPrint('[AppsProvider] load failed: $e\n$st');
      _error = e.toString();
    } finally {
      _loading = false;
      notifyListeners();
    }
  }
}
