import 'package:flutter/material.dart';

import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/upgrade_paywall.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/superwall_pilot.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The Plan & Usage row on the Settings sheet, plus — for Free and Plus — this month's minutes and
/// an Upgrade button, so upgrading is one tap from Settings instead of two.
class SettingsPlanSection extends StatelessWidget {
  const SettingsPlanSection({super.key, required this.row});

  /// The Plan & Usage row; tapping it still opens the Plan & Usage page.
  final Widget row;

  @override
  Widget build(BuildContext context) {
    final usage = context.watch<UsageProvider>();
    final subscription = usage.subscription;
    final plan = subscription?.subscription.plan;
    if (subscription == null || !usage.showSubscriptionUI || (plan != PlanType.basic && plan != PlanType.plus)) {
      return row;
    }
    final l10n = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        row,
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, 0, OmiSpacing.lg, OmiSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (subscription.transcriptionSecondsLimit > 0) ...[
                _MinutesMeter(subscription: subscription),
                const SizedBox(height: OmiSpacing.md),
              ],
              OmiButton(
                key: const ValueKey('settings_plan_upgrade'),
                label: plan == PlanType.plus ? l10n.upgradeToUnlimited : l10n.upgrade,
                expand: true,
                onPressed: () => openSettingsUpgrade(context, plan!),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// Free users go through the Superwall `settings_upgrade` placement when the pilot is on; Plus
/// users (and any fallback) get the existing plans sheet.
Future<void> openSettingsUpgrade(BuildContext context, PlanType plan) => openUpgradePaywall(
      context,
      placement: SuperwallPilot.settingsUpgradePlacement,
      source: 'Settings Plan Card',
      freeUser: plan == PlanType.basic,
    );

class _MinutesMeter extends StatelessWidget {
  const _MinutesMeter({required this.subscription});

  final UserSubscriptionResponse subscription;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final used = (subscription.transcriptionSecondsUsed / 60).round();
    final limit = (subscription.transcriptionSecondsLimit / 60).round();
    final ratio = (subscription.transcriptionSecondsUsed / subscription.transcriptionSecondsLimit).clamp(0.0, 1.0);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          l10n.minsUsedThisMonth(NumberFormat.decimalPattern(l10n.localeName).format(used), limit),
          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
        ),
        const SizedBox(height: OmiSpacing.xs),
        LinearProgressIndicator(
          value: ratio,
          backgroundColor: OmiColors.surface3,
          valueColor: AlwaysStoppedAnimation<Color>(ratio >= .8 ? OmiColors.warning : OmiColors.accent),
          minHeight: 4,
          borderRadius: OmiRadius.pillAll,
        ),
      ],
    );
  }
}
