import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/utils/logger.dart';
import 'package:superwallkit_flutter/superwallkit_flutter.dart';

/// Local development pilot. Production billing still uses Omi's existing flow.
///
/// Public SDK keys are supplied at build time, never committed to the repo.
class SuperwallPilot {
  SuperwallPilot._();

  static final SuperwallPilot instance = SuperwallPilot._();

  static const _testEnabled = bool.fromEnvironment('SUPERWALL_TEST_MODE');
  static const _iosKey = String.fromEnvironment('SUPERWALL_API_KEY_IOS');

  bool _configured = false;
  String? _identifiedUid;
  Future<void> _identityQueue = Future<void>.value();

  bool get isEnabled => _configured;

  void configure() {
    if (_configured ||
        !kDebugMode ||
        !_testEnabled ||
        Env.profile != AppEnvironmentProfile.localDev ||
        !Platform.isIOS ||
        _iosKey.isEmpty) {
      return;
    }

    try {
      Superwall.configure(_iosKey);
      _configured = true;
    } catch (error) {
      Logger.debug('Superwall pilot configuration failed: $error');
    }
  }

  /// Serialize account switches so an earlier identify cannot finish last.
  Future<void> syncUser(String? uid) {
    if (!_configured) return Future<void>.value();
    _identityQueue = _identityQueue.then((_) async {
      if (_identifiedUid == uid) return;
      try {
        if (_identifiedUid != null) {
          await Superwall.shared.reset();
          _identifiedUid = null;
        }
        if (uid != null) {
          await Superwall.shared.identify(uid);
          _identifiedUid = uid;
        }
      } catch (error) {
        Logger.debug('Superwall pilot identity update failed: $error');
      }
    });
    return _identityQueue;
  }

  /// Placement for the Upgrade button on the Settings plan card.
  static const settingsUpgradePlacement = 'settings_upgrade';

  /// Returns false if the pilot could not register its test placement.
  Future<bool> showUsageUpgrade(String uid) => showPlacement('omi_usage_upgrade_test', uid);

  /// Registers [placement] for [uid]. Returns false when the pilot is off or registration failed,
  /// so the caller can fall back to the existing plans sheet.
  Future<bool> showPlacement(String placement, String uid) async {
    if (!_configured) return false;
    await syncUser(uid);
    if (_identifiedUid != uid) return false;
    try {
      await Superwall.shared.registerPlacement(placement);
      return true;
    } catch (error) {
      Logger.debug('Superwall pilot placement failed: $error');
      return false;
    }
  }
}
