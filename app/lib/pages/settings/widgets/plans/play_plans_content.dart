import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/billing/play_billing.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

// Google Play Billing plan screens: the Play-priced plans sheet, the renewal and cancel disclosure
// shown under every Play purchase button, and the loading state before the billing provider is known.
typedef PlayUrlOpener = Future<bool> Function(Uri uri);

Future<bool> _openExternal(Uri uri) => launchUrl(uri, mode: LaunchMode.externalApplication);

/// PlansSheet body for a reader who buys through Google Play: Play's prices, Play's purchase sheet,
/// Restore, and Play's subscription center for a Play subscriber (on any platform). No Stripe offer,
/// code or link.
class PlayPlansContent extends StatefulWidget {
  const PlayPlansContent({super.key, required this.analyticsSource, this.openUrl, this.onPurchased});

  final String analyticsSource;

  /// Replaces the default close-on-purchase (a host page that must report its own result).
  final VoidCallback? onPurchased;

  /// Test seam for the Play subscription-center, Terms and Privacy links.
  final PlayUrlOpener? openUrl;

  @override
  State<PlayPlansContent> createState() => _PlayPlansContentState();
}

class _PlayPlansContentState extends State<PlayPlansContent> {
  String _interval = 'year';
  bool _busy = false;
  bool _pending = false;

  PlayUrlOpener get _open => widget.openUrl ?? _openExternal;

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
      if (!mounted) return;
      if (outcome == PaywallCheckoutOutcome.pending) setState(() => _pending = true);
      if (outcome != PaywallCheckoutOutcome.purchased) return;
      if (widget.onPurchased != null) {
        widget.onPurchased!();
      } else if (Navigator.of(context).canPop()) {
        Navigator.of(context).pop();
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _restore() async {
    setState(() => _busy = true);
    try {
      final usage = context.read<UsageProvider>();
      final outcome = await usage.restorePurchases();
      if (!mounted) return;
      final l10n = context.l10n;
      final refusal = usage.lastPlayRestoreRefusal;
      switch (outcome) {
        case RestoreOutcome.paid:
          OmiFeedback.confirm(context, l10n.unlimitedPlan);
        case RestoreOutcome.free when refusal != null:
          OmiFeedback.error(context, playRefusalMessage(l10n, refusal));
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
    final opened = await _open(playManageSubscriptionUri(productId));
    if (!opened && mounted) OmiFeedback.error(context, context.l10n.playManageSubscription);
  }

  @override
  Widget build(BuildContext context) {
    final usage = context.watch<UsageProvider>();
    final config = usage.playBilling;
    final sub = usage.subscription?.subscription;
    final subscriber = sub != null && sub.plan.isPaid && sub.billedByPlay;
    return DecoratedBox(
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.sheetTop),
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * 0.85,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xl, OmiSpacing.xl, OmiSpacing.md),
          children: subscriber
              ? _subscriber(context, sub, config?.productId ?? 'omi_pro')
              : config == null
                  ? const []
                  : _purchaser(context, usage),
        ),
      ),
    );
  }

  List<Widget> _subscriber(BuildContext context, Subscription sub, String productId) {
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
        onPressed: () => _manage(productId),
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
      if (_pending)
        Padding(
          padding: const EdgeInsets.only(top: OmiSpacing.sm),
          child: Text(l10n.playPurchasePending,
              key: const Key('play_purchase_pending'), textAlign: TextAlign.center, style: OmiType.subhead),
        ),
      const SizedBox(height: OmiSpacing.md),
      OmiButton(
        key: const Key('play_subscribe'),
        label: l10n.subscribe,
        expand: true,
        isLoading: _busy,
        onPressed: _busy || _pending ? null : () => _subscribe(selected, trialDays),
      ),
      const SizedBox(height: OmiSpacing.sm),
      TextButton(
        key: const Key('play_restore'),
        onPressed: _busy ? null : _restore,
        child: Text(l10n.restoreAction),
      ),
      PlayBillingDisclosure(openUrl: widget.openUrl),
    ];
  }
}

/// Under every Google Play purchase button: auto-renewal at the shown price, where to cancel, and the
/// Terms and Privacy links.
class PlayBillingDisclosure extends StatelessWidget {
  const PlayBillingDisclosure({super.key, this.openUrl, this.color, this.legalLinks = true});

  final PlayUrlOpener? openUrl;
  final Color? color;

  /// False where the host page already shows Terms and Privacy.
  final bool legalLinks;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final style = OmiType.footnote.copyWith(color: color ?? OmiColors.textSecondary);
    final open = openUrl ?? _openExternal;
    Widget link(Key key, String label, String url) => Semantics(
          link: true,
          child: InkWell(
            key: key,
            onTap: () => open(Uri.parse(url)),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
              child: Center(
                widthFactor: 1,
                child: Text(label, style: style.copyWith(decoration: TextDecoration.underline)),
              ),
            ),
          ),
        );
    return Column(
      children: [
        Text(l10n.playRenewalTerms, key: const Key('play_renewal_terms'), textAlign: TextAlign.center, style: style),
        Text(l10n.playBilledByGoogle, textAlign: TextAlign.center, style: style),
        if (legalLinks)
          Wrap(
            alignment: WrapAlignment.center,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              link(const Key('play_terms'), l10n.termsOfUse, AuthenticationProvider.termsOfServiceUrl),
              ExcludeSemantics(child: Text(' · ', style: style)),
              link(const Key('play_privacy'), l10n.privacyPolicy, AuthenticationProvider.privacyPolicyUrl),
            ],
          ),
      ],
    );
  }
}

/// The plans sheet's error state with its Retry, for paywalls that could not load Play's plans: the
/// subscription read failed (provider unknown) or Play offered no product.
class PlayPlansError extends StatelessWidget {
  const PlayPlansError({super.key});

  @override
  Widget build(BuildContext context) {
    final usage = context.watch<UsageProvider>();
    return OmiErrorState(
      key: const Key('play_plans_error'),
      title: context.l10n.unableToLoadPlans,
      message: context.l10n.checkConnectionTryAgain,
      onRetry: usage.billingProviderUnknown ? usage.fetchSubscription : usage.retryPlayOffers,
    );
  }
}

/// Shown while the billing provider is not known yet (Android before the first subscription read).
class PlayPlansLoading extends StatefulWidget {
  const PlayPlansLoading({super.key});

  @override
  State<PlayPlansLoading> createState() => _PlayPlansLoadingState();
}

class _PlayPlansLoadingState extends State<PlayPlansLoading> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<UsageProvider>().fetchSubscription();
    });
  }

  @override
  Widget build(BuildContext context) {
    final usage = context.watch<UsageProvider>();
    final failed = usage.error != null && !usage.isLoading;
    return DecoratedBox(
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.sheetTop),
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * 0.85,
        child: Padding(
          key: const Key('plans_provider_loading'),
          padding: const EdgeInsets.all(OmiSpacing.xl),
          child: failed
              ? OmiErrorState(
                  title: context.l10n.unableToLoadPlans,
                  message: context.l10n.checkConnectionTryAgain,
                  onRetry: usage.fetchSubscription,
                )
              : const Column(children: [PlanOptionShimmer(), SizedBox(height: 18), PlanOptionShimmer()]),
        ),
      ),
    );
  }
}
