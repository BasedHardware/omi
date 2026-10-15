import 'package:flutter/material.dart';

import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/upgrade_paywall.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Plan & Usage on the Settings sheet. For Free and Plus it is a plan card: the plan's name large
/// with a compact Upgrade beside it, then this month's minutes as a meter and a line of text, so
/// upgrading is one tap from Settings. Tapping the card outside the button opens the Plan & Usage
/// page. Every other plan (and no subscription yet) keeps the plain row.
class SettingsPlanSection extends StatelessWidget {
  const SettingsPlanSection({super.key, required this.row, required this.onOpen, this.planName});

  /// The plain Plan & Usage row, shown when there is nothing to upgrade to.
  final Widget row;

  /// Opens the Plan & Usage page.
  final VoidCallback onOpen;

  /// The plan's display name ("Free", the Plus plan's name).
  final String? planName;

  @override
  Widget build(BuildContext context) {
    final usage = context.watch<UsageProvider>();
    final subscription = usage.subscription;
    final plan = subscription?.subscription.plan;
    if (subscription == null || !usage.showSubscriptionUI || (plan != PlanType.basic && plan != PlanType.plus)) {
      return row;
    }
    final l10n = context.l10n;
    final hasLimit = subscription.transcriptionSecondsLimit > 0;
    final used = (subscription.transcriptionSecondsUsed / 60).round();
    final limit = (subscription.transcriptionSecondsLimit / 60).round();
    final ratio = hasLimit
        ? (subscription.transcriptionSecondsUsed / subscription.transcriptionSecondsLimit).clamp(0.0, 1.0)
        : 0.0;
    return Semantics(
      key: const ValueKey('settings_row_planAndUsage'),
      button: true,
      label: l10n.planAndUsage,
      child: InkWell(
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.md, OmiSpacing.md, OmiSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        ExcludeSemantics(
                          child: Text(
                            l10n.planAndUsage,
                            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                          ),
                        ),
                        const SizedBox(height: 2),
                        if (planName != null) Text(planName!, style: OmiType.title2),
                      ],
                    ),
                  ),
                  const SizedBox(width: OmiSpacing.md),
                  OmiButton(
                    key: const ValueKey('settings_plan_upgrade'),
                    label: plan == PlanType.plus ? l10n.upgradeToUnlimited : l10n.upgrade,
                    size: OmiButtonSize.compact,
                    onPressed: () => openSettingsUpgrade(context, plan!),
                  ),
                ],
              ),
              if (hasLimit) ...[
                const SizedBox(height: OmiSpacing.md),
                LinearProgressIndicator(
                  value: ratio,
                  backgroundColor: OmiColors.surface3,
                  valueColor: AlwaysStoppedAnimation<Color>(ratio >= .8 ? OmiColors.warning : OmiColors.accent),
                  minHeight: 6,
                  borderRadius: OmiRadius.pillAll,
                ),
                const SizedBox(height: OmiSpacing.xs),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        l10n.minsUsedThisMonth(NumberFormat.decimalPattern(l10n.localeName).format(used), limit),
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                      ),
                    ),
                    ExcludeSemantics(child: Icon(Icons.chevron_right, size: 20, color: OmiColors.textTertiary)),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// The Settings Upgrade button: the paywall experiment's arm for the reader, else the plans sheet.
Future<void> openSettingsUpgrade(BuildContext context, PlanType plan) => openUpgradePaywall(
      context,
      source: 'usage_page',
    );
