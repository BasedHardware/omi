import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

/// Home redesign A/B (PostHog flag `home-redesign`): `test` shows the redesigned Home (the bottom
/// recording pill with no top card, text-only empty states, pull-to-refresh,
/// page actions beside the switcher, upgrade in place, Tasks fold and menu, Omi's chat welcome,
/// starter to-dos); `control`, an unread flag or anything unexpected shows today's Home.
///
/// Client-evaluated. The arm is kept per account once PostHog assigns it, so a reader never
/// switches Home mid-session or between launches; a new assignment only takes effect on a Home the
/// reader has not seen yet this session (otherwise from the next launch). Exposure is PostHog's
/// `$feature_flag_called`, once per account and arm, sent when Home is first shown.
///
/// Pre-registration: `product/experiments/home-redesign.md`.
abstract final class HomeRedesign {
  /// PostHog flag key (project 302298). Registered in `config/feature-flags.yaml`.
  static const enabledFlag = 'home-redesign';
  static const testVariant = 'test';

  /// Debug-build override: `--dart-define=OMI_HOME_REDESIGN=on|off`.
  static const _debugOverride = String.fromEnvironment('OMI_HOME_REDESIGN');

  static final ValueNotifier<bool> _on = ValueNotifier(false);

  /// Whether this reader sees the redesigned Home. Listen to rebuild when the arm is first known.
  static ValueListenable<bool> get listenable => _on;
  static bool get on => _on.value;

  static bool _homeShown = false;
  static String? _loadedFor;

  static String _key(String uid) => 'experiments/home-redesign/arm/$uid';

  static bool? get _debugArm => switch (kDebugMode ? _debugOverride : '') {
        'on' => true,
        'off' => false,
        _ => null,
      };

  /// Applies the arm saved for the signed-in account (no network). Call at startup and after an
  /// account change.
  static void loadSaved({String? uid}) {
    final debug = _debugArm;
    if (debug != null) {
      _on.value = debug;
      return;
    }
    final id = uid ?? SharedPreferencesUtil().uid;
    _loadedFor = id;
    _on.value = id.isNotEmpty && SharedPreferencesUtil().getString(_key(id)) == testVariant;
  }

  /// Reads the flag for the signed-in account and saves the arm. Never moves a Home the reader is
  /// already looking at: a changed arm applies from the next launch.
  static Future<void> refresh({
    Future<String?> Function(String key)? readVariant,
    String? Function()? identity,
    String? uid,
    Duration identityWait = Duration.zero,
  }) async {
    if (_debugArm != null) return;
    final whoAmI = identity ?? () => AnalyticsManager().settledDistinctId;
    // Right after sign-in the analytics identity is still settling; flags read before it belong to
    // the anonymous id, where a per-account rollout never matches.
    final deadline = DateTime.now().add(identityWait);
    while (whoAmI() == null && DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    final who = whoAmI();
    final id = uid ?? SharedPreferencesUtil().uid;
    if (who == null || id.isEmpty) return;
    if (_loadedFor != id) loadSaved(uid: id);
    try {
      final variant = await (readVariant ?? AnalyticsManager().getFeatureFlagVariant)(enabledFlag);
      if (variant == null) return; // unresolved: keep what this account already has
      if (whoAmI() != who) return; // account switched mid-read
      SharedPreferencesUtil().saveString(_key(id), variant.trim());
      if (!_homeShown) _on.value = variant.trim() == testVariant;
    } catch (_) {
      // Keep the saved arm (or control) on any failure.
    }
  }

  static VoidCallback? _identityListener;

  /// Startup: the saved arm now, then the flag once the analytics identity settles (right after
  /// sign-in it is still the anonymous id, where a per-account rollout never matches). Listens for
  /// the identity instead of polling, so nothing keeps running.
  static void start() {
    loadSaved();
    if (AnalyticsManager().settledDistinctId != null) {
      refresh();
      return;
    }
    if (_identityListener != null) return;
    void onIdentity() {
      if (AnalyticsManager().settledDistinctId == null) return;
      AnalyticsManager.identityChanges.removeListener(_identityListener!);
      _identityListener = null;
      refresh();
    }

    _identityListener = onIdentity;
    AnalyticsManager.identityChanges.addListener(onIdentity);
  }

  /// Home is on screen: from now on the arm stays put this session, and the reader is exposed for the
  /// arm they actually see (only once PostHog has assigned one).
  static void markHomeShown({bool Function(String key, String variant)? record}) {
    _homeShown = true;
    final id = SharedPreferencesUtil().uid;
    if (_debugArm != null || id.isEmpty) return;
    final saved = SharedPreferencesUtil().getString(_key(id));
    if (saved.isEmpty) return;
    (record ?? AnalyticsManager().recordFeatureFlagExposure)(enabledFlag, on ? testVariant : 'control');
  }

  @visibleForTesting
  static void setForTesting(bool value) {
    _on.value = value;
    _homeShown = false;
  }

  @visibleForTesting
  static void resetForTesting() {
    if (_identityListener != null) AnalyticsManager.identityChanges.removeListener(_identityListener!);
    _identityListener = null;
    _on.value = false;
    _homeShown = false;
    _loadedFor = null;
  }
}
