import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The downsell shown once when the sign-up trial paywall is closed without a purchase: the same
/// Stripe checkout, with a 30-day trial instead of 7. Returns true when a trial was started.
abstract final class TrialUpsellSheet {
  static const int trialDays = 30;

  static Future<bool> show(BuildContext context, {required String source}) async {
    final usage = context.read<UsageProvider>();
    if (!usage.showSubscriptionUI) return false;
    if (usage.subscription?.subscription.plan.isPaid == true) return false;
    if (usage.subscription?.trialEligible != true) return false;
    if (usage.availablePlans == null) await usage.loadAvailablePlans();
    if (!context.mounted) return false;
    final offer = PaywallOffer.fromCatalog(usage.availablePlans);
    final price = offer?.yearly ?? offer?.monthly;
    if (offer == null || price == null) return false;
    PlatformManager.instance.analytics
        .track('Trial Upsell Shown', properties: {'source': source, 'trial_days': trialDays});
    final started = await showOmiSheet<bool>(
      context: context,
      showCloseButton: false,
      builder: (_) => _TrialUpsellBody(offer: offer, price: price, source: source),
    );
    if (started != true) {
      PlatformManager.instance.analytics.track('Trial Upsell Declined', properties: {'source': source});
    }
    return started == true;
  }
}

class _TrialUpsellBody extends StatefulWidget {
  const _TrialUpsellBody({required this.offer, required this.price, required this.source});

  final PaywallOffer offer;
  final PaywallPrice price;
  final String source;

  @override
  State<_TrialUpsellBody> createState() => _TrialUpsellBodyState();
}

class _TrialUpsellBodyState extends State<_TrialUpsellBody> {
  bool _busy = false;

  Future<void> _claim() async {
    if (_busy) return;
    setState(() => _busy = true);
    PlatformManager.instance.analytics.track('Trial Upsell Claimed', properties: {'source': widget.source});
    try {
      final outcome = await PaywallCheckout.start(
        context,
        priceId: widget.price.priceId,
        plan: widget.offer.tierId,
        interval: widget.price.interval,
        source: widget.source,
        trialDays: TrialUpsellSheet.trialDays,
      );
      if (!mounted) return;
      if (outcome == PaywallCheckoutOutcome.purchased) Navigator.of(context).pop(true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.lg, OmiSpacing.md, OmiSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l10n.trialUpsellTitle(TrialUpsellSheet.trialDays), style: OmiType.title2, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.sm),
          Text(
            l10n.trialUpsellBody(TrialUpsellSheet.trialDays),
            style: OmiType.body.copyWith(color: OmiColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: OmiSpacing.lg),
          // Same full pill as every other onboarding call to action (sign-in, paywall, walkthrough).
          OnboardingContinueButton(
            key: const Key('trial_upsell_claim'),
            label: _busy ? l10n.pleaseWait : l10n.trialUpsellClaim(TrialUpsellSheet.trialDays),
            onPressed: _busy ? () {} : _claim,
          ),
          const SizedBox(height: OmiSpacing.xs),
          OmiButton.tertiary(
            key: const Key('trial_upsell_decline'),
            label: l10n.noThanks,
            onPressed: _busy ? null : () => Navigator.of(context).pop(false),
          ),
        ],
      ),
    );
  }
}
