import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/billing/play_billing.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// PlansSheet body for a reader who buys through Google Play: Play's prices, Play's purchase sheet,
/// Restore, and Play's subscription center for a Play subscriber. No Stripe offer, code or link.
class PlayPlansContent extends StatefulWidget {
  const PlayPlansContent({super.key, required this.analyticsSource, this.openUrl});

  final String analyticsSource;

  /// Test seam for the Play subscription-center link.
  final Future<bool> Function(Uri uri)? openUrl;

  @override
  State<PlayPlansContent> createState() => _PlayPlansContentState();
}

class _PlayPlansContentState extends State<PlayPlansContent> {
  String _interval = 'year';
  bool _busy = false;

  Future<void> _subscribe(PlayPlanOffer offer, int? trialDays) async {
    setState(() => _busy = true);
    try {
      final outcome = await PaywallCheckout.start(
        context,
        priceId: 'play:${offer.basePlanId}',
        plan: 'unlimited_v2',
        interval: offer.interval,
        source: widget.analyticsSource,
        trialDays: trialDays,
      );
      if (outcome == PaywallCheckoutOutcome.purchased && mounted && Navigator.of(context).canPop()) {
        Navigator.of(context).pop();
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _restore() async {
    setState(() => _busy = true);
    try {
      final outcome = await context.read<UsageProvider>().restorePurchases();
      if (!mounted) return;
      final l10n = context.l10n;
      switch (outcome) {
        case RestoreOutcome.paid:
          OmiFeedback.confirm(context, l10n.unlimitedPlan);
        case RestoreOutcome.free:
          OmiFeedback.info(context, l10n.freePlan);
        case RestoreOutcome.failed:
          OmiFeedback.error(context, l10n.restorePurchasesFailed);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _manage(String productId) async {
    final uri = playManageSubscriptionUri(productId);
    await (widget.openUrl ?? (u) => launchUrl(u, mode: LaunchMode.externalApplication))(uri);
  }

  @override
  Widget build(BuildContext context) {
    final usage = context.watch<UsageProvider>();
    final config = usage.playBilling!;
    final sub = usage.subscription?.subscription;
    final subscriber = sub != null && sub.plan.isPaid && sub.billedByPlay;
    return DecoratedBox(
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.sheetTop),
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * 0.85,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xl, OmiSpacing.xl, OmiSpacing.md),
          children: subscriber ? _subscriber(context, sub, config) : _purchaser(context, usage),
        ),
      ),
    );
  }

  List<Widget> _subscriber(BuildContext context, Subscription sub, PlayBillingConfig config) {
    final l10n = context.l10n;
    final end = sub.currentPeriodEnd;
    final date = end == null ? null : OmiDateFormat.of(context).date(DateTime.fromMillisecondsSinceEpoch(end * 1000));
    return [
      Text(l10n.unlimitedPlan, style: OmiType.title3, textAlign: TextAlign.center),
      if (date != null) ...[
        const SizedBox(height: OmiSpacing.xs),
        Text(
          sub.cancelAtPeriodEnd
              ? l10n.yourPlanEndsOn(l10n.unlimitedPlan, date)
              : l10n.yourPlanWillRenewOn(l10n.unlimitedPlan, date),
          textAlign: TextAlign.center,
          style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
        ),
      ],
      const SizedBox(height: OmiSpacing.xl),
      OmiButton(
        key: const Key('play_manage_subscription'),
        label: l10n.playManageSubscription,
        expand: true,
        onPressed: () => _manage(config.productId),
      ),
      const SizedBox(height: OmiSpacing.sm),
      Text(l10n.playBilledByGoogle,
          textAlign: TextAlign.center, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
    ];
  }

  List<Widget> _purchaser(BuildContext context, UsageProvider usage) {
    final l10n = context.l10n;
    final offers = usage.playOffers;
    final trialEligible = usage.subscription?.trialEligible == true;
    final header = [
      Text(l10n.upgradeYourPlan, style: OmiType.title3, textAlign: TextAlign.center),
      const SizedBox(height: OmiSpacing.xs),
      Text(l10n.planSheetChooseYourPlan,
          textAlign: TextAlign.center, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
      const SizedBox(height: OmiSpacing.xl),
    ];
    if (offers == null) {
      return [
        ...header,
        if (usage.playOffersLoading)
          const Column(children: [PlanOptionShimmer(), SizedBox(height: 18), PlanOptionShimmer()])
        else
          OmiErrorState(
            title: l10n.unableToLoadPlans,
            message: l10n.checkConnectionTryAgain,
            onRetry: usage.retryPlayOffers,
          ),
      ];
    }
    final plans = [offers.yearly, offers.monthly].whereType<PlayPlanOffer>().toList();
    final selected = offers.forInterval(_interval) ?? plans.first;
    final trialDays = trialEligible ? selected.trialDays : null;
    return [
      ...header,
      for (final plan in plans) ...[
        PlanOptionCard(
          key: Key('play_plan_${plan.basePlanId}'),
          isSelected: plan.basePlanId == selected.basePlanId,
          title: plan.interval == 'year' ? l10n.billingYearly : l10n.billingMonthly,
          subtitle: null,
          price: l10n.billingRecurringPrice(plan.formattedPrice, plan.interval),
          onTap: () => setState(() => _interval = plan.interval),
        ),
        const SizedBox(height: OmiSpacing.md),
      ],
      if (trialDays != null && trialDays > 0)
        Text(l10n.billingTrialPrice(trialDays, selected.formattedPrice, selected.interval),
            textAlign: TextAlign.center, style: OmiType.subhead),
      const SizedBox(height: OmiSpacing.md),
      OmiButton(
        key: const Key('play_subscribe'),
        label: l10n.subscribe,
        expand: true,
        isLoading: _busy,
        onPressed: _busy ? null : () => _subscribe(selected, trialDays),
      ),
      const SizedBox(height: OmiSpacing.sm),
      TextButton(
        key: const Key('play_restore'),
        onPressed: _busy ? null : _restore,
        child: Text(l10n.restoreAction),
      ),
      Text(l10n.playBilledByGoogle,
          textAlign: TextAlign.center, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
    ];
  }
}
