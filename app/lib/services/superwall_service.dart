import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:omi/utils/logger.dart';
import 'package:superwallkit_flutter/superwallkit_flutter.dart';

/// Wraps the Superwall SDK so the rest of the app can call into it without
/// importing the package directly.
///
/// Standalone configuration (no `PurchaseController` / RevenueCat) — the SDK
/// drives StoreKit + Google Play Billing itself, validates receipts, and the
/// backend webhook (POST /v1/superwall/webhook) reconciles state. See
/// `plans/moonlit-petting-rocket.md` for the architecture write-up.
///
/// API keys are read from `--dart-define=SUPERWALL_API_KEY_IOS=…` /
/// `--dart-define=SUPERWALL_API_KEY_ANDROID=…` at build time so the values
/// don't ship in source. When unset, `initialize()` no-ops with a debug log
/// (lets the app boot without a Superwall workspace configured — useful for
/// local dev and pre-launch preview builds).
class SuperwallService {
  SuperwallService._();
  static final SuperwallService instance = SuperwallService._();

  static const _iosApiKey = String.fromEnvironment('SUPERWALL_API_KEY_IOS');
  static const _androidApiKey = String.fromEnvironment('SUPERWALL_API_KEY_ANDROID');

  bool _configured = false;
  StreamSubscription<SubscriptionStatus>? _statusSub;

  /// Configure the Superwall SDK. Idempotent — safe to call from app startup
  /// even if the user later signs out and back in.
  Future<void> initialize() async {
    if (_configured) return;

    final apiKey = Platform.isIOS ? _iosApiKey : (Platform.isAndroid ? _androidApiKey : '');
    if (apiKey.isEmpty) {
      if (kDebugMode) {
        Logger.debug(
          'SuperwallService.initialize: no API key for ${Platform.operatingSystem} — skipping. '
          'Set --dart-define=SUPERWALL_API_KEY_IOS=… / SUPERWALL_API_KEY_ANDROID=… to enable.',
        );
      }
      return;
    }

    try {
      // purchaseController = null → SDK manages StoreKit / Play Billing itself.
      Superwall.configure(
        apiKey,
        purchaseController: null,
        completion: () {
          _configured = true;
          Logger.debug('SuperwallService.initialize: configured');
        },
      );
    } catch (e, st) {
      Logger.error('SuperwallService.initialize failed: $e\n$st');
    }
  }

  /// Tag the current Superwall session with the omi `uid`. The webhook
  /// payload's `app_user_id` field will then carry this value, letting the
  /// backend handler resolve events to the right Firestore user doc.
  ///
  /// Call this whenever the signed-in uid changes (login, account switch).
  Future<void> identify(String uid) async {
    if (!_configured) return;
    if (uid.isEmpty) return;
    try {
      await Superwall.shared.identify(uid);
    } catch (e) {
      Logger.error('SuperwallService.identify($uid) failed: $e');
    }
  }

  /// Drop the user identity (sign-out) so the next session presents to a
  /// fresh anonymous user. Important to avoid cross-account entitlement leak
  /// when two people share a device.
  Future<void> reset() async {
    if (!_configured) return;
    try {
      await Superwall.shared.reset();
    } catch (e) {
      Logger.error('SuperwallService.reset failed: $e');
    }
  }

  /// Restore-purchases on a fresh install. Superwall checks the device's
  /// Apple ID / Google account receipts and re-applies the entitlement
  /// without firing a new purchase webhook (server-side state is already
  /// correct from the original purchase event).
  Future<RestorationResult?> restorePurchases() async {
    if (!_configured) return null;
    try {
      return await Superwall.shared.restorePurchases();
    } catch (e) {
      Logger.error('SuperwallService.restorePurchases failed: $e');
      return null;
    }
  }

  /// Subscribe to entitlement updates so callers can mirror the SDK's
  /// reactive state into a provider for snappy UI without waiting for the
  /// backend webhook to land. Pass [onChange] to receive each update.
  StreamSubscription<SubscriptionStatus>? listenToStatus(void Function(SubscriptionStatus) onChange) {
    if (!_configured) return null;
    try {
      _statusSub?.cancel();
      _statusSub = Superwall.shared.subscriptionStatus.listen(onChange);
      return _statusSub;
    } catch (e) {
      Logger.error('SuperwallService.listenToStatus failed: $e');
      return null;
    }
  }

  /// Tear down the entitlement subscription. Call from `dispose()` of any
  /// long-lived widget that registered a listener.
  Future<void> dispose() async {
    await _statusSub?.cancel();
    _statusSub = null;
  }
}
