import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/settings/payment_webview_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';
import 'package:omi/utils/cancel_pending_purchase.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

enum PaywallCheckoutOutcome { purchased, cancelled, failed }

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
    PlatformManager.instance.analytics.upgradePlanSelected(plan: plan, billingInterval: interval, source: source);
    try {
      final session = await provider.createUserCheckoutSession(priceId: priceId, trialDays: trialDays);
      if (!context.mounted) return PaywallCheckoutOutcome.cancelled;
      if (session != null && session['error'] == true) {
        // Checkout's 409 is an existing subscription, not a pending cancellation.
        report(
          session['status_code'] == 409
              ? l10n.checkoutExistingSubscription
              : session['detail'] as String? ?? l10n.couldNotProcessSubscription,
          error: true,
        );
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
        await provider.fetchSubscription();
        return PaywallCheckoutOutcome.purchased;
      }
      final url = session['url'] as String?;
      if (url == null) {
        report(l10n.couldNotProcessSubscription, error: true);
        return PaywallCheckoutOutcome.failed;
      }
      final completed = await routeToPage(context, PaymentWebViewPage(checkoutUrl: url));
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
      await provider.fetchSubscription();
      await provider.loadAvailablePlans();
      return PaywallCheckoutOutcome.purchased;
    } catch (_) {
      if (context.mounted) report(l10n.anErrorOccurredTryAgain, error: true);
      return PaywallCheckoutOutcome.failed;
    }
  }
}

/// The tier a free user is offered: the catalog's Unlimited tier, as two prices (month, year).
/// Null until the catalog has loaded; a catalog without an Unlimited tier yields no offer.
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

  /// Prefers the current Unlimited tier, then legacy Unlimited, then the most expensive tier.
  /// While a cancellation is pending, the offer is that subscription's current price instead,
  /// or null when the catalog does not contain it.
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
    final byTier = <String, List<Map<String, dynamic>>>{};
    for (final plan in plans) {
      final tier = plan['plan_id'];
      byTier.putIfAbsent(tier is String && tier.isNotEmpty ? tier : 'unlimited', () => []).add(plan);
    }
    String? tierId;
    for (final preferred in const ['unlimited_v2', 'unlimited']) {
      if (byTier.containsKey(preferred)) {
        tierId = preferred;
        break;
      }
    }
    tierId ??= byTier.keys.reduce((a, b) => _maxAmount(byTier[a]!) >= _maxAmount(byTier[b]!) ? a : b);
    final tierPlans = byTier[tierId]!;
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
      final currency = plan['currency'];
      final price = PaywallPrice(
        priceId: currentPriceId,
        interval: interval,
        amountMinor: amount.toInt(),
        currency: currency is String && currency.isNotEmpty ? currency.toLowerCase() : 'usd',
      );
      return PaywallOffer(
        tierId: tier is String && tier.isNotEmpty ? tier : 'unlimited',
        monthly: interval == 'month' ? price : null,
        yearly: interval == 'year' ? price : null,
        resubscribe: true,
      );
    }
    return null;
  }

  static num _maxAmount(List<Map<String, dynamic>> plans) =>
      plans.map((plan) => plan['unit_amount']).whereType<num>().fold<num>(0, (a, b) => a > b ? a : b);

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
  const PaywallPrice(
      {required this.priceId, required this.interval, required this.amountMinor, required this.currency});

  final String priceId;
  final String interval;
  final int amountMinor;
  final String currency;

  /// Per-month equivalent in minor units (a yearly price divided by twelve).
  int get perMonthMinor => interval == 'year' ? (amountMinor / 12).round() : amountMinor;
}
