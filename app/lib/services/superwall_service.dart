import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/subscription.dart' as omi;
import 'package:omi/pages/settings/payment_webview_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:provider/provider.dart';
import 'package:superwallkit_flutter/superwallkit_flutter.dart';

/// Wraps the Superwall SDK so the rest of the app can call into it without
/// importing the package directly.
///
/// Standalone configuration (no `PurchaseController` / RevenueCat) — the SDK
/// drives StoreKit + Google Play Billing itself, validates receipts, and the
/// backend webhook (POST /v1/superwall/webhook) reconciles state. See
/// `plans/moonlit-petting-rocket.md` for the architecture write-up.
///
/// API keys come from envied (``SUPERWALL_API_KEY_IOS`` /
/// ``SUPERWALL_API_KEY_ANDROID`` in ``.env`` / ``.dev.env``) so they're
/// obfuscated in the build alongside the other vendor secrets. When unset,
/// ``initialize()`` no-ops with a debug log so the app still boots in
/// pre-launch preview builds without a Superwall workspace configured.
class SuperwallService {
  SuperwallService._();
  static final SuperwallService instance = SuperwallService._();

  bool _configured = false;
  StreamSubscription<SubscriptionStatus>? _statusSub;
  StreamSubscription<SubscriptionStatus>? _conflictWatchSub;
  // Persisted under this key so the conflict toast doesn't re-fire across
  // app launches once the user has seen + dismissed it. Cleared by ops if
  // they want to re-trigger for a specific user (rare).
  static const _conflictPrefsKey = 'superwall_stripe_conflict_dialog_shown';

  /// Configure the Superwall SDK. Idempotent — safe to call from app startup
  /// even if the user later signs out and back in.
  Future<void> initialize() async {
    if (_configured) return;

    final apiKey = Platform.isIOS
        ? (Env.superwallApiKeyIos ?? '')
        : (Platform.isAndroid ? (Env.superwallApiKeyAndroid ?? '') : '');
    if (apiKey.isEmpty) {
      if (kDebugMode) {
        Logger.debug(
          'SuperwallService.initialize: no API key for ${Platform.operatingSystem} — skipping. '
          'Set SUPERWALL_API_KEY_IOS / SUPERWALL_API_KEY_ANDROID in .env (or .dev.env) and rerun '
          '`flutter pub run build_runner build --delete-conflicting-outputs`.',
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
    await _conflictWatchSub?.cancel();
    _conflictWatchSub = null;
  }

  /// Watch for the dual-billing-rail edge case: the user already had an active
  /// Stripe sub when they purchased a Superwall mobile sub, so they're now
  /// being charged twice across two providers. We can't auto-cancel the
  /// Stripe one (only the user can), so we surface a one-time dialog asking
  /// them to manage it. Per memory: shown at most once per install (persisted
  /// in shared prefs).
  ///
  /// Call once at app startup AFTER UsageProvider has had a chance to load
  /// the initial subscription state — typically right after authentication.
  Future<void> watchForStripeConflict() async {
    if (!_configured) return;
    if (_conflictWatchSub != null) return; // already watching
    if (SharedPreferencesUtil().getBool(_conflictPrefsKey)) return; // already shown once
    try {
      _conflictWatchSub = Superwall.shared.subscriptionStatus.listen((status) async {
        if (!status.isActive) return;
        // Only relevant on real devices that can purchase via App Store / Play.
        if (!(Platform.isIOS || Platform.isAndroid)) return;
        if (SharedPreferencesUtil().getBool(_conflictPrefsKey)) return;

        final ctx = globalNavigatorKey.currentContext;
        if (ctx == null || !ctx.mounted) return;
        final usage = ctx.read<UsageProvider>();
        // Refresh once so the source field reflects the latest webhook.
        await usage.fetchSubscription();
        if (!ctx.mounted) return;
        final sub = usage.subscription?.subscription;
        if (sub == null) return;
        // Two active billing rails for the same uid — the source field reflects
        // the LATEST write by the webhook (Superwall), but a stripe_subscription_id
        // also still pointing somewhere active is the conflict signal we care about.
        final hasStripe = (sub.stripeSubscriptionId ?? '').isNotEmpty;
        final isMobileSourced =
            sub.source == omi.SubscriptionSource.superwallIos || sub.source == omi.SubscriptionSource.superwallAndroid;
        if (!(hasStripe && isMobileSourced)) return;

        // Mark BEFORE showing — if the user dismisses by tapping outside the
        // sheet we still don't want to nag them on next launch.
        await SharedPreferencesUtil().saveBool(_conflictPrefsKey, true);
        if (!ctx.mounted) return;
        _showStripeConflictDialog(ctx);
      });
    } catch (e) {
      Logger.error('SuperwallService.watchForStripeConflict failed: $e');
    }
  }

  void _showStripeConflictDialog(BuildContext context) {
    final l10n = context.l10n;
    final title = l10n.dualSubscriptionDetectedTitle;
    final body = l10n.dualSubscriptionDetectedBody;
    final cancel = l10n.dualSubscriptionDetectedDismiss;
    final manage = l10n.dualSubscriptionDetectedManage;

    Future<void> openPortal(BuildContext dialogCtx) async {
      Navigator.of(dialogCtx).pop();
      final usage = dialogCtx.read<UsageProvider>();
      final portal = await usage.openCustomerPortal();
      final url = portal?['url'];
      if (url == null || url.isEmpty) return;
      final root = globalNavigatorKey.currentContext;
      if (root == null || !root.mounted) return;
      Navigator.of(root).push(
        MaterialPageRoute(builder: (_) => PaymentWebViewPage(checkoutUrl: url, title: manage)),
      );
    }

    showDialog<void>(
      context: context,
      builder: (dialogCtx) {
        final actions = [
          TextButton(
            onPressed: () => Navigator.of(dialogCtx).pop(),
            child: Text(cancel, style: const TextStyle(color: Colors.white)),
          ),
          TextButton(
            onPressed: () => openPortal(dialogCtx),
            child: Text(manage, style: const TextStyle(color: Colors.white)),
          ),
        ];
        if (PlatformService.isApple) {
          return CupertinoAlertDialog(title: Text(title), content: Text(body), actions: actions);
        }
        return AlertDialog(title: Text(title), content: Text(body), actions: actions);
      },
    );
  }
}
