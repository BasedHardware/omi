import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

/// Building blocks of the plans sheet (`plans_sheet.dart`).

/// One selectable plan: name, price, badges and what it includes.
class PlanOptionCard extends StatelessWidget {
  const PlanOptionCard({
    super.key,
    required this.isSelected,
    required this.title,
    required this.subtitle,
    required this.price,
    required this.onTap,
    this.saveTag,
    this.isPopular = false,
    this.isActive = false,
    this.endsOnDate,
    this.featureSummary,
    this.features = const [],
    this.desktopAccess,
  });

  final bool isSelected;
  final String title;
  final String? subtitle;
  final String price;
  final VoidCallback onTap;
  final String? saveTag;
  final bool isPopular;
  final bool isActive;
  final String? endsOnDate;
  final String? featureSummary;
  final List<String> features;
  final bool? desktopAccess;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.lg),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        border: Border.all(color: isSelected ? OmiColors.accent : Colors.transparent, width: 2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Main card area — tappable for plan selection.
          Semantics(
            button: true,
            selected: isSelected,
            inMutuallyExclusiveGroup: true,
            child: GestureDetector(
              onTap: onTap,
              behavior: HitTestBehavior.opaque,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (isPopular) ...[
                    PlanBadge(label: context.l10n.popularBadge, inverted: true),
                    const SizedBox(height: OmiSpacing.sm),
                  ],
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(title, style: OmiType.headline),
                            if (subtitle != null) ...[
                              const SizedBox(height: OmiSpacing.xxs),
                              Text(subtitle!, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                            ],
                          ],
                        ),
                      ),
                      const SizedBox(width: OmiSpacing.sm),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(price, style: OmiType.headline),
                          if (saveTag != null) ...[
                            const SizedBox(height: OmiSpacing.xs),
                            PlanBadge(label: saveTag!, color: OmiColors.successSurface),
                          ],
                          if (endsOnDate != null) ...[
                            const SizedBox(height: OmiSpacing.xs),
                            PlanBadge(label: context.l10n.endsOnDate(endsOnDate!), color: OmiColors.dangerSurface),
                          ] else if (isActive) ...[
                            const SizedBox(height: OmiSpacing.xs),
                            PlanBadge(label: context.l10n.active, color: OmiColors.surface3),
                          ],
                        ],
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          // Plan details — always visible (no expand/collapse toggle).
          if (featureSummary != null || desktopAccess != null || features.isNotEmpty) ...[
            const SizedBox(height: 10),
            if (featureSummary != null)
              Text(featureSummary!, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            if (featureSummary != null && (desktopAccess != null || features.isNotEmpty))
              const SizedBox(height: OmiSpacing.xs),
            // Desktop access — explicit ✓/✗ so Neo (mobile/web only) is clearly distinguished from
            // Operator/Architect.
            if (desktopAccess != null)
              _CheckLine(
                granted: desktopAccess!,
                text: desktopAccess! ? context.l10n.worksOnDesktop : context.l10n.noDesktopAccess,
              ),
            ...features.map((f) => _CheckLine(granted: true, text: f)),
          ],
        ],
      ),
    );
  }
}

class _CheckLine extends StatelessWidget {
  const _CheckLine({required this.granted, required this.text});

  final bool granted;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.xxs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ExcludeSemantics(
            child: Icon(
              granted ? Icons.check : Icons.close,
              color: granted ? OmiColors.success : OmiColors.danger,
              size: 14,
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              text,
              style: OmiType.footnote.copyWith(
                color: granted ? OmiColors.textSecondary : OmiColors.danger,
                height: 1.3,
                fontWeight: granted ? FontWeight.w400 : FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// A small label on a plan card ("POPULAR", "2 months free", "Active").
class PlanBadge extends StatelessWidget {
  const PlanBadge({super.key, required this.label, this.color = OmiColors.surface3, this.inverted = false});

  final String label;
  final Color color;

  /// White fill with a black label.
  final bool inverted;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(color: inverted ? OmiColors.accent : color, borderRadius: OmiRadius.smAll),
      child: Text(
        label,
        style: OmiType.caption.copyWith(
          color: inverted ? OmiColors.onAccent : OmiColors.textPrimary,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.3,
        ),
      ),
    );
  }
}

/// Loading placeholder with a plan card's shape.
class PlanOptionShimmer extends StatelessWidget {
  const PlanOptionShimmer({super.key});

  static Widget _bar(double height, double width) {
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface2,
      highlightColor: OmiColors.surface3,
      child: Container(
        height: height,
        width: width,
        decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xl + OmiSpacing.xs, OmiSpacing.md, OmiSpacing.lg),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        border: Border.all(color: OmiColors.border, width: 2),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [_bar(18, double.infinity), const SizedBox(height: OmiSpacing.xxs), _bar(14, 100)],
            ),
          ),
          const SizedBox(width: OmiSpacing.md),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [_bar(18, 100), const SizedBox(height: OmiSpacing.xs), _bar(14, 60)],
          ),
        ],
      ),
    );
  }
}

/// Yearly / Monthly selector above the tier cards.
class PlanBillingPeriodToggle extends StatelessWidget {
  const PlanBillingPeriodToggle({
    super.key,
    required this.isYearly,
    required this.savePercent,
    required this.onChanged,
  });

  final bool isYearly;
  final int? savePercent;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    Widget option({required bool yearly, required Widget child}) {
      final selected = yearly == isYearly;
      return Expanded(
        child: Semantics(
          button: true,
          selected: selected,
          inMutuallyExclusiveGroup: true,
          child: GestureDetector(
            onTap: () {
              HapticFeedback.lightImpact();
              onChanged(yearly);
            },
            child: Container(
              constraints: const BoxConstraints(minHeight: 48),
              padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm, horizontal: OmiSpacing.md),
              decoration: BoxDecoration(
                color: OmiColors.surface1,
                borderRadius: OmiRadius.pillAll,
                border: Border.all(color: selected ? OmiColors.accent : Colors.transparent, width: 2),
              ),
              child: DefaultTextStyle.merge(
                style: OmiType.subhead.copyWith(
                  color: selected ? OmiColors.textPrimary : OmiColors.textTertiary,
                  fontWeight: FontWeight.w600,
                ),
                child: Center(child: child),
              ),
            ),
          ),
        ),
      );
    }

    return Row(
      children: [
        option(
          yearly: true,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Flexible(child: Text(context.l10n.billingYearly)),
              if (savePercent != null) ...[
                const SizedBox(width: OmiSpacing.xs),
                PlanBadge(label: context.l10n.savePercent(savePercent!), color: OmiColors.successSurface),
              ],
            ],
          ),
        ),
        const SizedBox(width: OmiSpacing.sm),
        option(yearly: false, child: Text(context.l10n.billingMonthly, textAlign: TextAlign.center)),
      ],
    );
  }
}

/// An icon in an outlined square with a line of text: what a plan gives or what Free lacks.
class PlanFeatureItem extends StatelessWidget {
  const PlanFeatureItem({super.key, required this.icon, required this.text, this.isLimitation = false});

  final FaIconData icon;
  final String text;

  /// A Free-plan limitation, shown in the danger colour.
  final bool isLimitation;

  @override
  Widget build(BuildContext context) {
    final color = isLimitation ? OmiColors.danger : OmiColors.textPrimary;
    return Row(
      children: [
        ExcludeSemantics(
          child: Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: isLimitation ? OmiColors.dangerSurface : Colors.transparent,
              borderRadius: OmiRadius.smAll,
              border: Border.all(color: color),
            ),
            child: Center(child: FaIcon(icon, color: color, size: 16)),
          ),
        ),
        const SizedBox(width: OmiSpacing.sm),
        Expanded(
          child: Text(
            text,
            style: OmiType.callout.copyWith(color: color, fontWeight: isLimitation ? FontWeight.w500 : null),
          ),
        ),
      ],
    );
  }
}

/// A status box in place of the plan cards ("Upgrade scheduled", "You're on the annual plan").
class PlanStatusCard extends StatelessWidget {
  const PlanStatusCard({super.key, required this.icon, required this.title, required this.message, this.iconColor});

  final IconData icon;
  final String title;
  final String message;
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(OmiSpacing.lg),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        border: Border.all(color: OmiColors.border),
      ),
      child: Column(
        children: [
          ExcludeSemantics(child: Icon(icon, color: iconColor ?? OmiColors.textPrimary, size: 32)),
          const SizedBox(height: OmiSpacing.xs),
          Text(title, textAlign: TextAlign.center, style: OmiType.headline),
          const SizedBox(height: OmiSpacing.xxs),
          Text(message, textAlign: TextAlign.center, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
        ],
      ),
    );
  }
}

/// An icon and a sentence, used inside the plan-change dialogs.
class PlanDialogLine extends StatelessWidget {
  const PlanDialogLine({super.key, required this.icon, required this.text, this.color = OmiColors.textPrimary});

  final FaIconData icon;
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ExcludeSemantics(child: FaIcon(icon, color: color, size: 16)),
          const SizedBox(width: OmiSpacing.xs),
          Expanded(child: Text(text, textAlign: TextAlign.start, style: OmiType.subhead.copyWith(color: color))),
        ],
      ),
    );
  }
}
