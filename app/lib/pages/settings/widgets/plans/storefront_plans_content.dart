import 'package:flutter/material.dart';

import 'package:omi/models/plan_storefront.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Pure presentation: rank, recommendation, prices, copy and eligibility arrive from the server.
/// The host retains existing purchase/payment management calls and the close shell.
class StorefrontPlansContent extends StatefulWidget {
  const StorefrontPlansContent(
      {super.key,
      this.storefront,
      this.loading = false,
      this.failed = false,
      this.busy = false,
      this.livePlan,
      this.cancelScheduled = false,
      required this.onRetry,
      required this.onSelect,
      required this.onManage,
      required this.onRestore});

  final PlanStorefront? storefront;
  final bool loading;
  final bool failed;
  final bool busy;
  final PlanType? livePlan;
  final bool cancelScheduled;
  final Future<void> Function() onRetry;
  final Future<void> Function(StorefrontTier tier, StorefrontPrice price) onSelect;
  final Future<void> Function() onManage;
  final Future<void> Function() onRestore;

  @override
  State<StorefrontPlansContent> createState() => _StorefrontPlansContentState();
}

class _StorefrontPlansContentState extends State<StorefrontPlansContent> {
  // Annual is an explicit decision, never the default.
  String _interval = 'month';
  bool _otherPlansExpanded = false;

  @override
  Widget build(BuildContext context) {
    final data = widget.storefront;
    if (data != null && !data.showSubscriptionUi) return const SizedBox.shrink();
    final tiers = data?.tiers ?? const <StorefrontTier>[];
    final currentId = data?.current?.id;
    final visible = tiers.where((tier) => tier.recommended || tier.id == currentId).toList();
    final other = tiers.where((tier) => !tier.recommended && tier.id != currentId).toList();
    final ordered = [...visible.where((t) => t.recommended), ...visible.where((t) => !t.recommended)];
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.9,
      child: ListView(
        key: const Key('storefront_scroll'),
        padding: const EdgeInsets.all(OmiSpacing.md),
        children: [
          if (data?.current?.legacy != true && data?.usageContext != null) ...[
            Semantics(header: true, child: Text(data!.usageContext!.title, style: OmiType.headline)),
            const SizedBox(height: OmiSpacing.xxs),
            Text(data.usageContext!.message, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            const SizedBox(height: OmiSpacing.sm),
          ],
          if (data?.current?.legacy == true)
            _legacyPlan(data!.current!)
          else if (data?.current case final current?) ...[
            Text(
              [
                '${context.l10n.currentPlan} · ${current.name}',
                if (current.formattedPrice?.isNotEmpty == true) current.formattedPrice!,
                if (current.renewalLabel?.isNotEmpty == true) current.renewalLabel!,
              ].join(' · '),
              key: const Key('storefront_current_plan'),
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
            const SizedBox(height: OmiSpacing.sm),
          ],
          if (widget.loading)
            const OmiLoadingState()
          else if (widget.failed)
            OmiErrorState(
                title: context.l10n.unableToLoadPlans,
                message: context.l10n.checkConnectionTryAgain,
                onRetry: widget.onRetry)
          else if (data == null || data.tiers.isEmpty)
            OmiEmptyState(
                glyph: const SizedBox.shrink(),
                title: context.l10n.paywallNoPlans,
                action: OmiButton.secondary(label: context.l10n.refresh, onPressed: widget.onRetry))
          else if (data.current?.legacy != true) ...[
            Wrap(spacing: OmiSpacing.xs, children: [
              OmiFilterChip(
                  key: const Key('storefront_month'),
                  label: context.l10n.billingMonthly,
                  selected: _interval == 'month',
                  onSelected: () => setState(() => _interval = 'month')),
              OmiFilterChip(
                  key: const Key('storefront_year'),
                  label: context.l10n.billingYearly,
                  selected: _interval == 'year',
                  onSelected: () => setState(() => _interval = 'year')),
            ]),
            const SizedBox(height: OmiSpacing.sm),
            for (final tier in ordered.where((tier) => tier.recommended)) ...[
              _tierCard(tier, data.current),
              const SizedBox(height: OmiSpacing.sm),
            ],
            for (final tier in ordered.where((tier) => !tier.recommended)) ...[
              _tierCard(tier, data.current),
              const SizedBox(height: OmiSpacing.sm),
            ],
            if (other.isNotEmpty) ...[
              Semantics(
                expanded: _otherPlansExpanded,
                child: OmiButton.tertiary(
                  key: const Key('storefront_other_plans'),
                  label: context.l10n.paywallOtherPlans,
                  expand: true,
                  onPressed: () => setState(() => _otherPlansExpanded = !_otherPlansExpanded),
                ),
              ),
              if (_otherPlansExpanded)
                for (final tier in other) ...[
                  _tierCard(tier, data.current),
                  const SizedBox(height: OmiSpacing.sm),
                ],
            ],
          ],
          const SizedBox(height: OmiSpacing.sm),
          OmiButton.tertiary(
              key: const Key('storefront_restore'),
              label: context.l10n.refresh,
              onPressed: widget.busy ? null : widget.onRestore,
              expand: true),
          OmiButton.tertiary(
              key: const Key('storefront_manage'),
              label: context.l10n.managePaymentMethod,
              onPressed: widget.busy ? null : widget.onManage,
              expand: true),
        ],
      ),
    );
  }

  Widget _legacyPlan(StorefrontCurrentPlan current) {
    final line = [
      current.name,
      context.l10n.paywallLegacyPlan,
      if (current.formattedPrice?.isNotEmpty == true) current.formattedPrice!,
      if (current.renewalLabel?.isNotEmpty == true) current.renewalLabel!,
    ].join(' · ');
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text(line,
          key: const Key('storefront_current_plan'), style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
      const SizedBox(height: OmiSpacing.xs),
      Text(context.l10n.paywallLegacyPlanStays, key: const Key('storefront_legacy_stays'), style: OmiType.subhead),
      const SizedBox(height: OmiSpacing.sm),
    ]);
  }

  Widget _tierCard(StorefrontTier tier, StorefrontCurrentPlan? current) {
    final price = tier.priceFor(_interval);
    final isCurrentPrice = price != null && price.id == current?.priceId;
    final storefront = widget.storefront!;
    final decision = price == null
        ? StorefrontCheckoutDecision.refuse
        : storefrontCheckoutDecision(
            storefront.current,
            widget.livePlan,
            tier,
            price,
            usageLegacy: storefront.usageContext?.legacy == true,
            cancelScheduled: widget.cancelScheduled,
            showSubscriptionUi: storefront.showSubscriptionUi,
          );
    return Container(
      key: Key('storefront_tier_${tier.id}'),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        border:
            Border.all(color: tier.recommended ? OmiColors.accent : OmiColors.border, width: tier.recommended ? 2 : 1),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Wrap(
            alignment: WrapAlignment.spaceBetween,
            spacing: OmiSpacing.xs,
            runSpacing: OmiSpacing.xxs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Semantics(header: true, child: Text(tier.name, style: OmiType.title3)),
              if (tier.recommended)
                Text(context.l10n.paywallRecommended, style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600)),
            ]),
        const SizedBox(height: OmiSpacing.xxs),
        const SizedBox(height: OmiSpacing.sm),
        if (price != null) ...[
          Text(price.monthlyEquivalent, key: Key('storefront_price_${tier.id}'), style: OmiType.title3),
          Text(price.formatted, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          if (_interval == 'year' && price.annualSavings != null)
            Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.xs),
                child: Text(price.annualSavings!, style: OmiType.footnote)),
          const SizedBox(height: OmiSpacing.sm),
        ],
        if (price != null) ...[
          const SizedBox(height: OmiSpacing.xs),
          Text(price.renewalTerms, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
        ],
        if (price case final selected? when decision != StorefrontCheckoutDecision.refuse) ...[
          const SizedBox(height: OmiSpacing.sm),
          OmiButton(
              key: Key('storefront_buy_${tier.id}'),
              label: decision == StorefrontCheckoutDecision.resubscribe ? context.l10n.resubscribe : tier.actionLabel,
              expand: true,
              isLoading: widget.busy,
              onPressed: widget.busy ? null : () => widget.onSelect(tier, selected)),
        ] else if (isCurrentPrice) ...[
          const SizedBox(height: OmiSpacing.xs),
          Text(context.l10n.currentPlan, style: OmiType.footnote),
        ],
        const SizedBox(height: OmiSpacing.sm),
        Text(tier.description, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
        if (tier.recommended && storefront.usageContext?.source == 'mcp_daily_cap')
          Padding(
              padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
              child: Text('• ${context.l10n.paywallMcpDailyRequests}',
                  key: const Key('storefront_mcp_benefit'), style: OmiType.subhead)),
        if (tier.recordingEquivalent != null)
          Padding(
              padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
              child: Text(tier.recordingEquivalent!, style: OmiType.callout)),
        for (final outcome in tier.outcomes)
          Padding(
              padding: const EdgeInsets.only(bottom: OmiSpacing.xs), child: Text('• $outcome', style: OmiType.subhead)),
      ]),
    );
  }
}
