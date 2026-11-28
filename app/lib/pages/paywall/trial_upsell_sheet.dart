import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The downsell shown once when the sign-up trial paywall is closed without a purchase: the same
/// Stripe checkout, with a 30-day trial instead of 7. Returns true when a trial was started, false
/// when the sheet was declined, and null when nothing was shown.
abstract final class TrialUpsellSheet {
  static const int trialDays = 30;

  static Future<bool?> show(BuildContext context, {required String source}) async {
    final usage = context.read<UsageProvider>();
    if (!usage.showSubscriptionUI) return null;
    if (usage.subscription?.subscription.plan.isPaid == true) return null;
    if (usage.subscription?.trialEligible != true) return null;
    // Stripe-only 30-day trial: Google Play sells only its own 7-day trial offer.
    if (usage.playBilledPurchaser) return null;
    if (usage.availablePlans == null) await usage.loadAvailablePlans();
    if (!context.mounted) return null;
    final offer = PaywallOffer.fromCatalog(usage.availablePlans);
    final price = offer?.yearly ?? offer?.monthly;
    if (offer == null || price == null) return null;
    PlatformManager.instance.analytics
        .track('Trial Upsell Shown', properties: {'source': source, 'trial_days': trialDays});
    final started = await showOmiSheet<bool>(
      context: context,
      showCloseButton: false,
      builder: (_) => TrialUpsellContent(offer: offer, price: price, source: source),
    );
    if (started != true) {
      PlatformManager.instance.analytics.track('Trial Upsell Declined', properties: {'source': source});
    }
    return started == true;
  }
}

class TrialUpsellContent extends StatefulWidget {
  const TrialUpsellContent({super.key, required this.offer, required this.price, required this.source, this.checkout});

  final PaywallOffer offer;
  final PaywallPrice price;
  final String source;

  /// Hermetic preview/test seam; production uses the shared checkout.
  final Future<PaywallCheckoutOutcome> Function(BuildContext, PaywallPrice, String)? checkout;

  @override
  State<TrialUpsellContent> createState() => TrialUpsellContentState();
}

class TrialUpsellContentState extends State<TrialUpsellContent> {
  bool _busy = false;
  bool _closed = false;

  Future<void> _claim() async {
    if (_busy) return;
    setState(() => _busy = true);
    PlatformManager.instance.analytics.track('Trial Upsell Claimed', properties: {'source': widget.source});
    try {
      final outcome = widget.checkout != null
          ? await widget.checkout!(context, widget.price, widget.offer.tierId)
          : await PaywallCheckout.start(
              context,
              priceId: widget.price.priceId,
              plan: widget.offer.tierId,
              interval: widget.price.interval,
              source: widget.source,
              trialDays: TrialUpsellSheet.trialDays,
            );
      if (!mounted) return;
      if (_closed) return;
      if (outcome == PaywallCheckoutOutcome.purchased || outcome == PaywallCheckoutOutcome.alreadyPaid) {
        _closed = true;
        Navigator.of(context).pop(outcome == PaywallCheckoutOutcome.purchased);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    // This Stripe trial is never sold on a Play build: close if Play setup arrives while it is open.
    // Only while this sheet is the top route, so it never pops a route above it.
    if (context.select<UsageProvider, bool>((usage) => usage.buysThroughPlay) &&
        !_closed &&
        ModalRoute.of(context)?.isCurrent == true) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || _closed || ModalRoute.of(context)?.isCurrent != true) return;
        _closed = true;
        Navigator.of(context).pop(false);
      });
    }
    // One scroll: at the largest text sizes the price, Claim and No Thanks are taller than a pinned
    // footer can be, so they scroll in together under the terms, with both labels wrapping in full.
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.lg, OmiSpacing.md, OmiSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l10n.trialUpsellTitle(TrialUpsellSheet.trialDays), style: OmiType.title2, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.sm),
          // Card and charge terms are purchase information: full-contrast text.
          Text(
            l10n.trialUpsellBody(TrialUpsellSheet.trialDays),
            key: const Key('trial_upsell_body'),
            style: OmiType.body.copyWith(color: OmiColors.textPrimary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: OmiSpacing.sm),
          // The price, Claim and No Thanks stop growing at 2x, like the sign-in buttons, so the whole
          // price stays on screen with the whole Claim label on a small phone at the largest text.
          MediaQuery.withClampedTextScaling(
            maxScaleFactor: 2,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  widget.price.trialLabel(context, TrialUpsellSheet.trialDays),
                  key: const Key('trial_upsell_price_terms'),
                  style: OmiType.headline,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: OmiSpacing.lg),
                // The onboarding pill at default size; grows and wraps instead of clipping at large text.
                OmiButton(
                  key: const Key('trial_upsell_claim'),
                  label: _busy ? l10n.pleaseWait : l10n.trialUpsellClaim(TrialUpsellSheet.trialDays),
                  onPressed: _busy ? () {} : () => unawaited(_claim()),
                  expand: true,
                  pill: true,
                  maxLines: null,
                  height: 56,
                  labelStyle: OmiType.headline,
                ),
                const SizedBox(height: OmiSpacing.xs),
                OmiButton.tertiary(
                  key: const Key('trial_upsell_decline'),
                  label: l10n.noThanks,
                  expand: true,
                  maxLines: null,
                  onPressed: _busy ? null : () => Navigator.of(context).pop(false),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
