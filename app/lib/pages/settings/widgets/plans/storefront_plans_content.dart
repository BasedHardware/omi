import 'package:flutter/material.dart';

import 'package:omi/models/plan_storefront.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Pure presentation. Rank, recommendation, prices, copy, and eligibility arrive from the server.
/// The host retains purchase and payment-management calls and the close shell.
class StorefrontPlansContent extends StatefulWidget {
  const StorefrontPlansContent({
    super.key,
    this.storefront,
    this.loading = false,
    this.failed = false,
    this.busy = false,
    this.livePlan,
    this.cancelScheduled = false,
    required this.onRetry,
    required this.onSelect,
    required this.onManage,
  });

  final PlanStorefront? storefront;
  final bool loading;
  final bool failed;
  final bool busy;
  final PlanType? livePlan;
  final bool cancelScheduled;
  final Future<void> Function() onRetry;
  final Future<void> Function(StorefrontTier tier, StorefrontPrice price) onSelect;
  final Future<void> Function() onManage;

  @override
  State<StorefrontPlansContent> createState() => _StorefrontPlansContentState();
}

class _StorefrontPlansContentState extends State<StorefrontPlansContent> {
  // Monthly is the default. Yearly is an explicit choice.
  String _interval = 'month';
  bool _allPlansExpanded = false;

  bool _cancelScheduled(PlanStorefront? data) => widget.cancelScheduled || data?.current?.cancelAtPeriodEnd == true;

  @override
  Widget build(BuildContext context) {
    final data = widget.storefront;
    if (data != null && !data.showSubscriptionUi) return const SizedBox.shrink();
    final legacy = data?.current?.legacy == true;
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.9,
      child: ListView(
        key: const Key('storefront_scroll'),
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.md),
        children: [
          if (data != null) ...[
            Semantics(header: true, child: Text(data.header, style: OmiType.headline)),
            if (data.current != null) ...[
              const SizedBox(height: OmiSpacing.xs),
              Text(
                data.current!.line,
                key: const Key('storefront_current_plan'),
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
              ),
              if (legacy && data.current!.legacyNote != null) ...[
                const SizedBox(height: OmiSpacing.xs),
                Text(data.current!.legacyNote!, key: const Key('storefront_legacy_note'), style: OmiType.subhead),
              ],
            ],
            const SizedBox(height: OmiSpacing.sm),
          ],
          if (widget.loading)
            const OmiLoadingState()
          else if (widget.failed)
            OmiErrorState(
              message: context.l10n.paywallLoadError,
              retryLabel: context.l10n.paywallTryAgain,
              onRetry: widget.onRetry,
            )
          else if (data == null || (data.tiers.isEmpty && !legacy))
            OmiEmptyState(
              glyph: const SizedBox.shrink(),
              title: context.l10n.paywallNoPlans,
            )
          else if (!legacy)
            ..._plans(data),
          if (data == null || data.current?.legacy == true || data.current?.priceId != null || widget.failed) ...[
            const SizedBox(height: OmiSpacing.sm),
            OmiButton.tertiary(
              key: const Key('storefront_manage'),
              label: context.l10n.paywallManageBilling,
              onPressed: widget.busy ? null : widget.onManage,
              expand: true,
            ),
          ],
        ],
      ),
    );
  }

  List<Widget> _plans(PlanStorefront data) {
    final tiers = data.tiers;
    final primary = tiers.where((tier) => tier.recommended || tier.isCurrent).toList();
    final rest = tiers.where((tier) => !tier.recommended && !tier.isCurrent).toList();
    return [
      Wrap(spacing: OmiSpacing.xs, runSpacing: OmiSpacing.xxs, children: [
        OmiFilterChip(
          key: const Key('storefront_month'),
          label: context.l10n.billingMonthly,
          selected: _interval == 'month',
          onSelected: () => setState(() => _interval = 'month'),
        ),
        OmiFilterChip(
          key: const Key('storefront_year'),
          label: data.yearlyToggleLabel ?? context.l10n.billingYearly,
          selected: _interval == 'year',
          onSelected: () => setState(() => _interval = 'year'),
        ),
      ]),
      const SizedBox(height: OmiSpacing.sm),
      for (final tier in primary) ...[
        _tierCard(tier, data),
        const SizedBox(height: OmiSpacing.sm),
      ],
      if (rest.isNotEmpty) ...[
        Semantics(
          expanded: _allPlansExpanded,
          child: OmiButton.tertiary(
            key: const Key('storefront_other_plans'),
            label: context.l10n.paywallOtherPlans,
            expand: true,
            onPressed: () => setState(() => _allPlansExpanded = !_allPlansExpanded),
          ),
        ),
        if (_allPlansExpanded)
          for (final tier in rest) ...[
            const SizedBox(height: OmiSpacing.sm),
            _tierCard(tier, data),
          ],
      ],
    ];
  }

  Widget _tierCard(StorefrontTier tier, PlanStorefront storefront) {
    final price = tier.priceFor(_interval);
    final decision = price == null
        ? StorefrontCheckoutDecision.refuse
        : storefrontCheckoutDecision(
            storefront.current,
            widget.livePlan,
            tier,
            price,
            cancelScheduled: _cancelScheduled(storefront),
            showSubscriptionUi: storefront.showSubscriptionUi,
          );
    final cta = price == null
        ? null
        : storefrontActionLabel(current: storefront.current, tier: tier, price: price, decision: decision);
    final compact = tier.isCurrent;
    return Container(
      key: Key('storefront_tier_${tier.planId}'),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        border:
            Border.all(color: tier.recommended ? OmiColors.accent : OmiColors.border, width: tier.recommended ? 2 : 1),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: Semantics(header: true, child: Text(tier.name, style: OmiType.title3))),
          Wrap(spacing: OmiSpacing.xxs, runSpacing: OmiSpacing.xxs, alignment: WrapAlignment.end, children: [
            if (tier.recommended) _badge(context.l10n.paywallRecommended),
            if (tier.isCurrent) _badge(context.l10n.paywallYourPlan),
          ]),
        ]),
        if (price != null) ...[
          const SizedBox(height: OmiSpacing.xs),
          Text(price.headline, key: Key('storefront_price_${tier.planId}'), style: OmiType.title3),
          if (price.subline != null)
            Padding(
              padding: const EdgeInsets.only(top: OmiSpacing.xxs),
              child: Text(price.subline!,
                  key: Key('storefront_subline_${tier.planId}'),
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ),
        ],
        const SizedBox(height: OmiSpacing.sm),
        Text(tier.hoursLine, style: OmiType.subhead),
        if (!compact) ...[
          const SizedBox(height: OmiSpacing.xs),
          for (final bullet in tier.bullets)
            Padding(
              padding: const EdgeInsets.only(bottom: OmiSpacing.xxs),
              child: Text('• $bullet', style: OmiType.subhead),
            ),
        ],
        if (price != null && cta != null) ...[
          SizedBox(height: compact ? OmiSpacing.sm : OmiSpacing.xs),
          OmiButton(
            key: Key('storefront_buy_${tier.planId}'),
            label: cta,
            expand: true,
            isLoading: widget.busy,
            onPressed: widget.busy ? null : () => widget.onSelect(tier, price),
          ),
          const SizedBox(height: OmiSpacing.xxs),
          Text(
            price.renewalLine,
            key: Key('storefront_renewal_${tier.planId}'),
            style: OmiType.caption.copyWith(color: OmiColors.textSecondary),
          ),
        ],
      ]),
    );
  }

  Widget _badge(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: 2),
      decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.pillAll),
      child: Text(label, style: OmiType.caption.copyWith(fontWeight: FontWeight.w600)),
    );
  }
}
