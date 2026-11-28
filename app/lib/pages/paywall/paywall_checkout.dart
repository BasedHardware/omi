import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/backend/http/api/payment.dart' show paymentRefusalMessage, useGooglePlayCode;
import 'package:omi/pages/settings/payment_webview_page.dart';
import 'package:omi/services/billing/play_billing.dart';
import 'package:omi/utils/analytics/registry/events.g.dart' show UpgradeBillingProviderStage;
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';
import 'package:omi/utils/cancel_pending_purchase.dart';
import 'package:omi/utils/billing_price.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// [pending]: Google Play accepted a purchase whose payment has not cleared; nothing to retry or upsell.
/// [alreadyPaid]: the reader already has a paid plan billed outside Google Play on a build that sells through
/// Play, so no Stripe Checkout starts; the paywall closes with nothing bought.
enum PaywallCheckoutOutcome { purchased, cancelled, failed, pending, alreadyPaid }

/// The purchase path shared by every paywall variant: the same Stripe Checkout session and in-app
/// webview the `PlansSheet` uses for a free user, with the same analytics. Variants only change
/// what the reader sees before tapping; nothing about how money moves.
abstract final class PaywallCheckout {
  static Future<PaywallCheckoutOutcome> start(
    BuildContext context, {
    required String priceId,
    required String plan,
    required String interval,
    required String source,
    void Function(String message)? surface,
    int? trialDays,
  }) async {
    final provider = context.read<UsageProvider>();
    final l10n = context.l10n;
    final subscription = provider.subscription?.subscription;
    final previousPlan = subscription?.plan.wireName ?? 'basic';
    void report(String message, {required bool error}) {
      surface?.call(message);
      if (!context.mounted) return;
      if (error) {
        OmiFeedback.error(context, message);
      } else {
        OmiFeedback.confirm(context, message);
      }
    }

    if (cancelPendingPurchase(
          cancelAtPeriodEnd: subscription?.cancelAtPeriodEnd == true,
          currentPriceId: subscription?.currentPriceId,
          priceId: priceId,
        ) ==
        CancelPendingPurchase.blocked) {
      report(l10n.resubscribeFirstToChangePlans, error: true);
      return PaywallCheckoutOutcome.failed;
    }
    if (provider.playBilledPurchaser) {
      return _startPlay(context, plan: plan, interval: interval, source: source, report: report, trialDays: trialDays);
    }
    // A build that sells through Google Play starts no Stripe Checkout. A paid Stripe reader (a paywall still
    // open when Play setup or the plan arrived) may only reactivate the same price while its cancel is pending.
    final reactivateOnly = provider.buysThroughPlay;
    if (reactivateOnly &&
        cancelPendingPurchase(
              cancelAtPeriodEnd: subscription?.cancelAtPeriodEnd == true,
              currentPriceId: subscription?.currentPriceId,
              priceId: priceId,
            ) !=
            CancelPendingPurchase.resubscribe) {
      return PaywallCheckoutOutcome.alreadyPaid;
    }
    PlatformManager.instance.analytics.upgradePlanSelected(plan: plan, billingInterval: interval, source: source);
    try {
      final session = await provider.createUserCheckoutSession(priceId: priceId, trialDays: trialDays);
      if (!context.mounted) return PaywallCheckoutOutcome.cancelled;
      if (session != null && session['error'] == true) {
        // Checkout's 409 is an existing subscription, not a pending cancellation.
        report(
          paymentRefusalMessage(session) ??
              (session['status_code'] == 409
                  ? l10n.checkoutExistingSubscription
                  : session['detail'] as String? ?? l10n.couldNotProcessSubscription),
          error: true,
        );
        // The server now sells this client through Google Play: read the plan again so the paywall shows Play.
        if (session['code'] == useGooglePlayCode) await provider.fetchSubscription(fresh: true);
        return PaywallCheckoutOutcome.failed;
      }
      if (session == null) {
        report(l10n.couldNotLaunchUpgradePage, error: true);
        return PaywallCheckoutOutcome.failed;
      }
      if (session['status'] == 'reactivated') {
        final date = billingDateLabel(context, session['next_billing_date']) ??
            billingDateLabel(context, subscription?.currentPeriodEnd);
        final planName = currentPlanDisplayName(context, provider.subscription);
        final message = date == null ? l10n.subscriptionReactivatedDefault : l10n.yourPlanWillRenewOn(planName, date);
        report(message, error: false);
        PlatformManager.instance.analytics
            .upgradeSucceeded(previousPlan: previousPlan, newPlan: plan, billingInterval: interval);
        await provider.fetchSubscription(fresh: true);
        return PaywallCheckoutOutcome.purchased;
      }
      // Never open Stripe Checkout on a build that sells through Google Play, even when that became known while
      // the request was in flight; a reactivation answers `reactivated` above, never with a Checkout URL.
      if (reactivateOnly || provider.buysThroughPlay) {
        return provider.playBilledPurchaser ? PaywallCheckoutOutcome.failed : PaywallCheckoutOutcome.alreadyPaid;
      }
      final url = session['url'] as String?;
      if (url == null) {
        report(l10n.couldNotProcessSubscription, error: true);
        return PaywallCheckoutOutcome.failed;
      }
      final completed = await routeToPage(
          context,
          PaymentWebViewPage(
            checkoutUrl: url,
            onCheckoutOpened: () => PlatformManager.instance.analytics
                .checkoutOpened(plan: plan, billingInterval: interval, source: source, inApp: true),
            onCheckoutCompleted: () => PlatformManager.instance.analytics
                .checkoutCompleted(plan: plan, billingInterval: interval, source: source, inApp: true),
          ));
      if (completed != true) {
        PlatformManager.instance.analytics.upgradeCancelled();
        return PaywallCheckoutOutcome.cancelled;
      }
      if (context.mounted) {
        // A trial checkout charges nothing today; say so instead of the paid-checkout message.
        report(
          trialDays != null && trialDays > 0 ? l10n.paywallTrialStarted(trialDays) : l10n.subscriptionSuccessfulCharged,
          error: false,
        );
      }
      PlatformManager.instance.analytics
          .upgradeSucceeded(previousPlan: previousPlan, newPlan: plan, billingInterval: interval);
      await provider.fetchSubscription(fresh: true);
      await provider.loadAvailablePlans();
      return PaywallCheckoutOutcome.purchased;
    } catch (_) {
      if (context.mounted) report(l10n.anErrorOccurredTryAgain, error: true);
      return PaywallCheckoutOutcome.failed;
    }
  }
}

/// Google Play Billing: Play's sheet in the user's currency, then the server confirms the entitlement.
Future<PaywallCheckoutOutcome> _startPlay(
  BuildContext context, {
  required String plan,
  required String interval,
  required String source,
  required void Function(String message, {required bool error}) report,
  int? trialDays,
}) async {
  final provider = context.read<UsageProvider>();
  final l10n = context.l10n;
  final analytics = PlatformManager.instance.analytics;
  final config = provider.playBilling!;
  final offer = provider.playOffers?.forInterval(interval);
  if (offer == null) {
    report(l10n.couldNotLaunchUpgradePage, error: true);
    return PaywallCheckoutOutcome.failed;
  }
  final previousPlan = provider.subscription?.subscription.plan.wireName ?? 'basic';
  analytics.upgradePlanSelected(plan: plan, billingInterval: interval, source: source);
  analytics.playBillingStage(stage: UpgradeBillingProviderStage.selected, billingInterval: interval);
  final withTrial = trialDays != null && trialDays > 0 && provider.subscription?.trialEligible == true;
  final result = await provider.playBillingService.purchase(
    offer: offer,
    withTrial: withTrial,
    obfuscatedAccountId: config.obfuscatedAccountId,
  );
  switch (result.outcome) {
    case PlayPurchaseOutcome.purchased:
      await provider.fetchSubscription(fresh: true);
      final days = withTrial ? offer.trialDays : null;
      report(days != null && days > 0 ? l10n.paywallTrialStarted(days) : l10n.subscriptionSuccessfulCharged,
          error: false);
      analytics.upgradeSucceeded(previousPlan: previousPlan, newPlan: plan, billingInterval: interval);
      analytics.playBillingStage(stage: UpgradeBillingProviderStage.succeeded, billingInterval: interval);
      return PaywallCheckoutOutcome.purchased;
    case PlayPurchaseOutcome.pending:
      report(l10n.playPurchasePending, error: false);
      analytics.playBillingStage(stage: UpgradeBillingProviderStage.pending, billingInterval: interval);
      return PaywallCheckoutOutcome.pending;
    case PlayPurchaseOutcome.cancelled:
      analytics.upgradeCancelled();
      analytics.playBillingStage(stage: UpgradeBillingProviderStage.cancelled, billingInterval: interval);
      return PaywallCheckoutOutcome.cancelled;
    case PlayPurchaseOutcome.failed:
      report(playRefusalMessage(l10n, result.code), error: true);
      analytics.playBillingStage(stage: UpgradeBillingProviderStage.failed, billingInterval: interval);
      return PaywallCheckoutOutcome.failed;
  }
}

/// User-facing text for a Play purchase the server did not confirm.
String playRefusalMessage(AppLocalizations l10n, String? code) {
  return switch (code) {
    'stripe_subscription_active' => l10n.checkoutExistingSubscription,
    'purchase_owned_elsewhere' => l10n.playPurchaseOtherAccount,
    _ => l10n.playPurchaseNotConfirmed,
  };
}

/// The tier a free user is offered: the catalog's Omi Pro (`unlimited_v2`) tier, as two prices
/// (month, year). Null until the catalog has loaded; a catalog without Omi Pro yields no offer.
@immutable
class PaywallOffer {
  const PaywallOffer({
    required this.tierId,
    required this.monthly,
    required this.yearly,
    this.resubscribe = false,
  });

  final String tierId;
  final PaywallPrice? monthly;
  final PaywallPrice? yearly;

  /// True when this offer is the price already on a cancellation-pending subscription.
  final bool resubscribe;

  /// Only Omi Pro is offered; a retired tier is never a fallback.
  /// While a cancellation is pending, the offer is that subscription's current price instead,
  /// or null when the catalog does not contain it.
  /// Play's prices for a Play-billed reader (null until Play answers); the server catalog otherwise.
  static PaywallOffer? forUsage(UsageProvider usage, {bool cancelAtPeriodEnd = false, String? currentPriceId}) {
    if (usage.billingProviderUnknown) return null;
    if (usage.playBilledPurchaser) {
      final offers = usage.playOffers;
      return offers == null ? null : fromPlay(offers);
    }
    return fromCatalog(usage.availablePlans, cancelAtPeriodEnd: cancelAtPeriodEnd, currentPriceId: currentPriceId);
  }

  static PaywallOffer? fromPlay(PlayOffers offers) {
    PaywallPrice? price(PlayPlanOffer? plan) => plan == null
        ? null
        : PaywallPrice(
            priceId: 'play:${plan.basePlanId}',
            interval: plan.interval,
            amountMinor: playMinorUnits(plan.priceMicros, plan.currencyCode),
            currency: plan.currencyCode.toLowerCase(),
            display: plan.formattedPrice,
            trialDisplay: plan.trialFormattedPrice,
            trialDays: plan.trialFormattedPrice == null ? null : plan.trialDays,
          );
    final offer = PaywallOffer(tierId: 'unlimited_v2', monthly: price(offers.monthly), yearly: price(offers.yearly));
    return offer.monthly == null && offer.yearly == null ? null : offer;
  }

  static PaywallOffer? fromCatalog(
    Map<String, dynamic>? catalog, {
    bool cancelAtPeriodEnd = false,
    String? currentPriceId,
  }) {
    final raw = catalog?['plans'];
    if (raw is! List) return null;
    final plans = raw.whereType<Map>().map((plan) => Map<String, dynamic>.from(plan)).toList();
    if (plans.isEmpty) return null;
    if (cancelAtPeriodEnd) return _currentPriceOffer(plans, currentPriceId);
    const tierId = 'unlimited_v2';
    final tierPlans = plans.where((plan) => plan['plan_id'] == tierId).toList();
    if (tierPlans.isEmpty) return null;
    PaywallPrice? price(String interval) {
      for (final plan in tierPlans) {
        if (plan['interval'] != interval) continue;
        final id = plan['id'];
        final amount = plan['unit_amount'];
        if (id is! String || amount is! num) continue;
        final currency = plan['currency'];
        return PaywallPrice(
          priceId: id,
          interval: interval,
          amountMinor: amount.toInt(),
          currency: currency is String && currency.isNotEmpty ? currency.toLowerCase() : 'usd',
        );
      }
      return null;
    }

    final offer = PaywallOffer(tierId: tierId, monthly: price('month'), yearly: price('year'));
    return offer.monthly == null && offer.yearly == null ? null : offer;
  }

  static PaywallOffer? _currentPriceOffer(List<Map<String, dynamic>> plans, String? currentPriceId) {
    if (currentPriceId == null || currentPriceId.isEmpty) return null;
    for (final plan in plans) {
      if (plan['id'] != currentPriceId) continue;
      final interval = plan['interval'];
      if (interval != 'month' && interval != 'year') return null;
      final amount = plan['unit_amount'];
      if (amount is! num) return null;
      final tier = plan['plan_id'];
      if (tier is! String || tier.isEmpty) return null;
      final currency = plan['currency'];
      final price = PaywallPrice(
        priceId: currentPriceId,
        interval: interval,
        amountMinor: amount.toInt(),
        currency: currency is String && currency.isNotEmpty ? currency.toLowerCase() : 'usd',
      );
      return PaywallOffer(
        tierId: tier,
        monthly: interval == 'month' ? price : null,
        yearly: interval == 'year' ? price : null,
        resubscribe: true,
      );
    }
    return null;
  }

  /// Whole-percent saving of the yearly price against twelve monthly payments, or null.
  int? get yearlySavingPercent {
    final month = monthly;
    final year = yearly;
    if (month == null || year == null || month.amountMinor <= 0) return null;
    final percent = ((1 - year.amountMinor / (month.amountMinor * 12)) * 100).round();
    return percent <= 0 ? null : percent;
  }
}

@immutable
class PaywallPrice {
  const PaywallPrice({
    required this.priceId,
    required this.interval,
    required this.amountMinor,
    required this.currency,
    this.display,
    this.trialDisplay,
    this.trialDays,
  });

  final String priceId;
  final String interval;
  final int amountMinor;
  final String currency;

  /// Google Play's own price string; shown as-is when set.
  final String? display;

  /// Google Play's own string for the free-trial phase, when Play lists a trial for this account.
  final String? trialDisplay;

  /// Google Play's free-trial length for this account; null when Play lists no free trial phase.
  final int? trialDays;

  String get formatted => display ?? formatBillingPrice(amountMinor, currency);

  String get formattedPerMonth => formatBillingPrice(perMonthMinor, currency);

  String recurringLabel(BuildContext context) => context.l10n.billingRecurringPrice(formatted, interval);

  String trialLabel(BuildContext context, int days) => context.l10n.billingTrialPrice(days, formatted, interval);

  /// Per-month equivalent in minor units (a yearly price divided by twelve).
  int get perMonthMinor => interval == 'year' ? (amountMinor / 12).round() : amountMinor;
}
