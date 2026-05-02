import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:nooto_v2/apps/app_model.dart';
import 'package:nooto_v2/apps/apps_storage.dart';
import 'package:nooto_v2/services/api_client.dart';
import 'package:nooto_v2/services/auth_service.dart';

/// Signature for the launch-url seam. Mirrors `url_launcher`'s `launchUrl`
/// so production callers pass it through unchanged; tests inject a fake that
/// records the URL instead of opening Safari.
typedef LaunchUrlFn = Future<bool> Function(Uri uri, {LaunchMode mode});

/// Default launcher — production path. Wrapped so the typedef matches
/// `url_launcher`'s named-arg signature exactly.
Future<bool> _defaultLaunchUrl(Uri uri, {LaunchMode mode = LaunchMode.platformDefault}) {
  return launchUrl(uri, mode: mode);
}

/// Default uid resolver — production path. Reads the current Firebase user.
Future<String?> _defaultGetUid() async => AuthService.instance.currentUser?.uid;

/// Owns the Apps marketplace state — the catalog from `/v2/apps` and the
/// user's installed-set from `/v1/apps/enabled`. Install/uninstall update
/// the local set optimistically and roll back on backend error.
///
/// OAuth-style installs (Jira, Linear, ClickUp, …) extend the install path:
/// `/v1/apps/enable` returns `400 "App setup is not completed"` until the
/// user has authorized the plugin. We open the plugin's auth URL in the
/// system browser; the plugin then redirects back via
/// `nooto://app-setup-complete?app_id=…&status=…`, which the deep-link
/// listener in main.dart hands to [handleSetupComplete] to retry the install.
///
/// Two-way-sync (writeback) opt-in is stored in Hive box `apps.prefs.v1`
/// and defaults to false for any app — surprise writes are a trust hazard.
class AppsProvider extends ChangeNotifier {
  AppsProvider({
    required ApiClient client,
    LaunchUrlFn? launchUrl,
    Future<String?> Function()? getUid,
  })  : _client = client,
        _launchUrl = launchUrl ?? _defaultLaunchUrl,
        _getUid = getUid ?? _defaultGetUid {
    _hydrateTwoWaySync();
  }

  final ApiClient _client;
  final LaunchUrlFn _launchUrl;
  final Future<String?> Function() _getUid;

  /// Backend's machine-readable signal for "needs OAuth". Lifted into a const
  /// so the install/handleSetupComplete branches can't drift apart.
  static const String _setupNotCompleted = 'App setup is not completed';

  /// Hive key inside [AppsBoxes.prefs] for the writeback opt-in map.
  static const String _twoWaySyncKey = 'twoWaySync';

  /// Status payload from `nooto://app-setup-complete` that means the user
  /// finished the OAuth flow successfully. Anything else is a failure / cancel.
  static const String _setupSuccess = 'success';

  List<AppGroup> _groups = const [];
  Set<String> _enabledIds = const {};
  bool _loading = false;
  bool _hasFetched = false;
  String? _error;
  String? _pendingId; // app currently mid-install/uninstall

  /// In-memory map of per-app writeback opt-in. Persisted to Hive box
  /// `apps.prefs.v1` so a relaunch keeps the toggle state. Defaults to false
  /// for any app not in the map.
  Map<String, bool> _twoWaySyncByAppId = const {};

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
  /// rolls back if the backend rejects.
  ///
  /// Returns true on a clean install. Returns false in three cases:
  ///   * already installed / another install in flight (no-op)
  ///   * backend rejected and we rolled back
  ///   * backend asked for OAuth setup — we kept the optimistic enable in
  ///     place and opened the plugin's auth URL; the eventual deep-link
  ///     callback ([handleSetupComplete]) retries enable. The "false" here
  ///     tells the caller "the install isn't actually done yet — OAuth is
  ///     in flight" so e.g. a confirm sheet can stay open.
  Future<bool> install(String appId) async {
    if (_pendingId != null || _enabledIds.contains(appId)) return false;
    _pendingId = appId;
    _enabledIds = {..._enabledIds, appId};
    notifyListeners();
    try {
      await _client.post('v1/apps/enable?app_id=$appId');
      return true;
    } catch (e) {
      // ApiError(400, "App setup is not completed") signals an OAuth-style
      // plugin — open the browser and keep the optimistic enable. Every
      // other failure (other 4xx, 5xx, network drop, decode error) is a
      // hard failure — roll back.
      if (e is ApiError &&
          e.statusCode == 400 &&
          e.detail == _setupNotCompleted) {
        return await _startOAuthFlow(appId);
      }
      debugPrint('[AppsProvider] install($appId) failed: $e');
      _enabledIds = {..._enabledIds}..remove(appId);
      _error = e.toString();
      return false;
    } finally {
      _pendingId = null;
      notifyListeners();
    }
  }

  /// Opens the plugin's OAuth URL in the system browser. Keeps the optimistic
  /// enable in place — desktop-v2 mirrors this so the row stays "Installed"
  /// through the OAuth round-trip; [handleSetupComplete] retries enable when
  /// the plugin redirects back. Rolls back on no-auth-url and on launch errors.
  Future<bool> _startOAuthFlow(String appId) async {
    final app = _findApp(appId);
    final target = app?.externalIntegration?.primaryAuthUrl;
    if (target == null || target.isEmpty) {
      debugPrint('[AppsProvider] install($appId): setup required but no auth URL');
      _enabledIds = {..._enabledIds}..remove(appId);
      _error = 'App setup is required but no auth URL is configured.';
      return false;
    }
    final uid = await _getUid();
    final url = (uid != null && uid.isNotEmpty)
        ? '$target${target.contains('?') ? '&' : '?'}uid=${Uri.encodeQueryComponent(uid)}'
        : target;
    try {
      await _launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
      debugPrint('[AppsProvider] opened OAuth setup: $url');
      // Optimistic enable stays in place — handleSetupComplete will retry
      // /v1/apps/enable on success or roll back on failure.
      return false;
    } catch (e) {
      debugPrint('[AppsProvider] failed to open setup URL for $appId: $e');
      _enabledIds = {..._enabledIds}..remove(appId);
      _error = 'Could not open browser for app setup.';
      return false;
    }
  }

  /// Uninstall the app. Optimistic with rollback, mirrors [install].
  Future<bool> uninstall(String appId) async {
    if (_pendingId != null || !_enabledIds.contains(appId)) return false;
    _pendingId = appId;
    _enabledIds = {..._enabledIds}..remove(appId);
    notifyListeners();
    try {
      await _client.post('v1/apps/disable?app_id=$appId');
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

  /// Called by main.dart's deep-link listener when a plugin reports OAuth
  /// completion via `nooto://app-setup-complete?app_id=X&status=Y`.
  ///
  /// On success: reload apps from the server (so we have fresh enabled state)
  /// and retry [install] for the app if the server doesn't already have us
  /// as enabled. On error: roll back the optimistic enable, surface the
  /// error, and reload to get the truth from the server.
  Future<void> handleSetupComplete(String appId, String status) async {
    if (status != _setupSuccess) {
      // Plugin reported an error. Roll back the optimistic enable, reload to
      // get fresh state, then re-stamp the error — load() resets `_error` at
      // the start of every call, so it must be re-applied after.
      _enabledIds = {..._enabledIds}..remove(appId);
      await load(force: true);
      _error = 'OAuth failed: $status';
      notifyListeners();
      return;
    }
    await load(force: true);
    // After reload, the server may already have us as enabled (some plugins
    // flip enabled themselves on OAuth completion). If not — and the app is
    // still in our local catalog — retry install: the plugin's OAuth
    // completion means the next enable call won't return the 400.
    if (!_enabledIds.contains(appId) && _findApp(appId) != null) {
      await install(appId);
    }
  }

  /// Per-app writeback opt-in. Defaults to false for any app id not in the
  /// map — surprise writes to a source tracker (Jira, Linear, …) are a trust
  /// hazard. UI must surface this explicitly in Settings -> Apps -> [appId].
  bool isTwoWaySyncEnabled(String appId) => _twoWaySyncByAppId[appId] ?? false;

  /// Flip the writeback opt-in for an app and persist to Hive. Notifies so
  /// any toggle UI rebuilds in the same frame.
  Future<void> setTwoWaySync(String appId, bool enabled) async {
    _twoWaySyncByAppId = {..._twoWaySyncByAppId, appId: enabled};
    await _persistTwoWaySync();
    notifyListeners();
  }

  NooApp? _findApp(String appId) {
    for (final group in _groups) {
      for (final app in group.apps) {
        if (app.id == appId) return app;
      }
    }
    return null;
  }

  void _hydrateTwoWaySync() {
    try {
      final box = Hive.box<Map>(AppsBoxes.prefs);
      final raw = box.get(_twoWaySyncKey);
      if (raw is Map) {
        _twoWaySyncByAppId = Map<String, bool>.from(
          raw.map((k, v) => MapEntry(k.toString(), v == true)),
        );
      }
    } catch (e) {
      // Box not open (e.g. main.dart hasn't wired it yet, or running in a
      // test that didn't open it). Default to empty — a missing toggle map
      // is the same as "no opt-ins yet" and never blocks the provider boot.
      debugPrint('[AppsProvider] _hydrateTwoWaySync failed: $e');
    }
  }

  Future<void> _persistTwoWaySync() async {
    try {
      await Hive.box<Map>(AppsBoxes.prefs).put(_twoWaySyncKey, _twoWaySyncByAppId);
    } catch (e) {
      debugPrint('[AppsProvider] _persistTwoWaySync failed: $e');
    }
  }
}
