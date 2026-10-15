import 'package:flutter/material.dart';

import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/upgrade_paywall.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The Plan & Usage row on the Settings sheet, plus — for Free and Plus — this month's minutes and
/// a compact Upgrade button beside them, so upgrading is one tap from Settings instead of two.
class SettingsPlanSection extends StatelessWidget {
  const SettingsPlanSection({super.key, required this.row});

  /// The Plan & Usage row; tapping it still opens the Plan & Usage page.
  final Widget row;

  /// Where an [OmiSettingsRow]'s title starts: its padding, the 24 pt icon column and the gap.
  static const double _titleInset = OmiSpacing.md + 24 + OmiSpacing.md;

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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        row,
        // Under the row and aligned with its title: this month's minutes with a compact Upgrade
        // beside them, then the meter across the card, so the card reads as the plan rather than
        // as a full-width button.
        Padding(
          padding: const EdgeInsets.fromLTRB(_titleInset, 0, OmiSpacing.md, OmiSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Expanded(
                    child: hasLimit
                        ? Text(
                            l10n.minsUsedThisMonth(NumberFormat.decimalPattern(l10n.localeName).format(used), limit),
                            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                          )
                        : const SizedBox.shrink(),
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
                const SizedBox(height: OmiSpacing.sm),
                LinearProgressIndicator(
                  value: ratio,
                  backgroundColor: OmiColors.surface3,
                  valueColor: AlwaysStoppedAnimation<Color>(ratio >= .8 ? OmiColors.warning : OmiColors.accent),
                  minHeight: 4,
                  borderRadius: OmiRadius.pillAll,
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

/// The Settings Upgrade button: the paywall experiment's arm for the reader, else the plans sheet.
Future<void> openSettingsUpgrade(BuildContext context, PlanType plan) => openUpgradePaywall(
      context,
      source: 'usage_page',
    );
