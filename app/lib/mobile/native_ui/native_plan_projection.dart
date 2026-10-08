import 'package:flutter/material.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';

import 'ios_native_surface.dart';

/// Project the owner's already-filtered plan cards and their exact selection callbacks.
/// Prices, audience, active/cancelled badges and entitlement copy come from those cards.
List<NativeRow>? nativePlanRows(AppLocalizations l10n, Widget cards, {required bool enabled}) {
  final rows = <NativeRow>[];
  bool collect(Widget widget) {
    if (widget is Column) return widget.children.every(collect);
    if (widget is Padding) return collect(widget.child!);
    if (widget is SizedBox) return widget.child == null || collect(widget.child!);
    if (widget is PlanBillingPeriodToggle) {
      rows.add(NativeRow('plan_period', l10n.changePlan,
          kind: 'choice',
          value: widget.isYearly ? 'year' : 'month',
          enabled: enabled,
          options: {
            'year':
                [l10n.billingYearly, if (widget.savePercent != null) l10n.savePercent(widget.savePercent!)].join(' · '),
            'month': l10n.billingMonthly
          },
          action: (value) => widget.onChanged(value == 'year')));
      return true;
    }
    if (widget is! PlanOptionCard || widget.key is! ValueKey<String>) return false;
    rows.add(NativeRow('plan_${(widget.key! as ValueKey<String>).value}', widget.title,
        symbol: widget.isSelected ? 'checkmark.circle.fill' : 'circle',
        enabled: enabled,
        subtitle: [
          widget.price,
          widget.subtitle,
          widget.saveTag,
          if (widget.isPopular) l10n.popularBadge,
          if (widget.endsOnDate != null) l10n.endsOnDate(widget.endsOnDate!),
          if (widget.endsOnDate == null && widget.isActive) l10n.active,
          widget.featureSummary,
          if (widget.desktopAccess != null) widget.desktopAccess! ? l10n.worksOnDesktop : l10n.noDesktopAccess,
          ...widget.features,
        ].whereType<String>().where((line) => line.isNotEmpty).join('\n'),
        action: (_) => widget.onTap()));
    return true;
  }

  if (!collect(cards) || rows.map((row) => row.id).toSet().length != rows.length) return null;
  return rows;
}
