import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:firebase_auth/firebase_auth.dart';

import 'package:omi/utils/logger.dart';
import 'package:superwallkit_flutter/superwallkit_flutter.dart';

/// Local development pilot. Production billing still uses Omi's existing flow.
///
/// Public SDK keys are supplied at build time, never committed to the repo.
class SuperwallPilot {
  SuperwallPilot._();

  static final SuperwallPilot instance = SuperwallPilot._();

  /// Off unless a debug build passes `--dart-define=SUPERWALL_TEST_MODE=true`; otherwise every
  /// upgrade entry point goes through the paywall experiment (`PaywallRouter`).
  static const _testEnabled = bool.fromEnvironment('SUPERWALL_TEST_MODE');

  /// The pilot's own Superwall test project (public SDK key, meant to ship inside apps). Production
  /// needs Omi's Superwall project and its App Store Connect in-app purchase products instead.
  static const _iosKey = String.fromEnvironment('SUPERWALL_API_KEY_IOS', defaultValue: 'pk_EA03aegLVEAIuDfWT5zTB');

  bool _configured = false;
  String? _identifiedUid;
  Future<void> _identityQueue = Future<void>.value();

  bool get isEnabled => _configured;

  /// The end of onboarding just offered a plan; the device tutorial that follows on Home skips its
  /// own offer so nobody sees two paywalls in a row.
  bool offeredDuringOnboarding = false;

  void configure() {
    if (_configured || !kDebugMode || !_testEnabled || !Platform.isIOS || _iosKey.isEmpty) {
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

  /// Upgrade on the Plan & Usage page, and that page's automatic offer when opened from Transcription
  /// Settings → View usage.
  static const usageUpgradePlacement = 'usage_upgrade';
  static const transcriptionSettingsPlacement = 'transcription_settings_usage';

  /// Free chat limit reached (the sheet opens automatically over chat).
  static const chatQuotaPlacement = 'chat_quota';

  /// Chat Apps Pro gate (Telegram / iMessage rows and the Pro card).
  static const chatAppsPlacement = 'chat_apps';

  /// Plus transcription meter crossing its threshold (queued until recording stops).
  static const plusMeterPlacement = 'plus_meter';

  /// Placement for the Upgrade button on the Settings plan card.
  static const settingsUpgradePlacement = 'settings_upgrade';

  /// Placement for tapping a conversation or memory locked after the free minutes run out.
  static const lockedContentPlacement = 'locked_content';

  /// Placement shown to anyone not subscribed when the device tutorial closes (finished, skipped or
  /// replayed). Superwall only: no plans-sheet fallback, so nothing changes when the pilot is off.
  static const deviceSetupCompletePlacement = 'device_setup_complete';

  /// The paywall re-ask on app open for free users (`PaywallReask`, flag `paywall-reask`).
  static const appOpenReaskPlacement = 'app_open_reask';

  /// Shows [placement] for the current user and completes once the paywall closes. Returns false
  /// when nothing was shown (pilot off, no paywall for this user, or an error), so the caller can
  /// fall back to the plans sheet.
  Future<bool> showPlacementAndWait(String placement) async {
    if (!_configured) return false;
    final user = FirebaseAuth.instance.currentUser;
    if (user == null || user.isAnonymous) return false;
    await syncUser(user.uid);
    if (_identifiedUid != user.uid) return false;
    final closed = Completer<bool>();
    final handler = PaywallPresentationHandler()
      ..onDismiss((_, __) {
        if (!closed.isCompleted) closed.complete(true);
      })
      ..onSkip((_) {
        if (!closed.isCompleted) closed.complete(false);
      })
      ..onError((_) {
        if (!closed.isCompleted) closed.complete(false);
      });
    try {
      await Superwall.shared.registerPlacement(placement, handler: handler);
    } catch (error) {
      Logger.debug('Superwall pilot placement failed: $error');
      return false;
    }
    // A paywall whose close is never reported must not hold onboarding: treat it as closed.
    return closed.future.timeout(const Duration(minutes: 5), onTimeout: () => true);
  }

  /// [showPlacement] for the signed-in, non-anonymous Firebase user.
  Future<bool> showPlacementForCurrentUser(String placement) async {
    if (!_configured) return false;
    final user = FirebaseAuth.instance.currentUser;
    if (user == null || user.isAnonymous) return false;
    return showPlacement(placement, user.uid);
  }

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
