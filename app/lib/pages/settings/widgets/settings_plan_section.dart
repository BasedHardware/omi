import 'package:flutter/material.dart';

import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/upgrade_paywall.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/settings_plan_card_experiment.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Plan & Usage on the Settings sheet. Every plan but Free and Plus (and no subscription yet) keeps
/// the plain row. Free and Plus get one of two layouts from the `settings-plan-card` A/B
/// ([SettingsPlanCardExperiment]): control keeps the row with the minutes meter and a full-width
/// Upgrade under it; `card` is a plan card with the plan name large, the meter, then a full-width
/// Upgrade, and tapping the card outside the button opens the Plan & Usage page.
class SettingsPlanSection extends StatefulWidget {
  const SettingsPlanSection({super.key, required this.row, required this.onOpen, this.planName, this.arm});

  /// The plain Plan & Usage row, shown when there is nothing to upgrade to.
  final Widget row;

  /// Opens the Plan & Usage page.
  final VoidCallback onOpen;

  /// The plan's display name ("Free", the Plus plan's name).
  final String? planName;

  /// Forces an arm (tests); null reads the experiment.
  final SettingsPlanCardArm? arm;

  @override
  State<SettingsPlanSection> createState() => _SettingsPlanSectionState();
}

class _SettingsPlanSectionState extends State<SettingsPlanSection> {
  SettingsPlanCardArm? _arm;
  bool _exposed = false;

  @override
  void initState() {
    super.initState();
    _arm = widget.arm ?? SettingsPlanCardExperiment.cached;
    if (widget.arm == null) {
      SettingsPlanCardExperiment.resolve().then((arm) {
        if (mounted && arm != _arm) setState(() => _arm = arm);
      });
    }
  }

  /// Counts the reader once the section is drawn for Free or Plus with the arm PostHog assigned.
  void _expose(SettingsPlanCardArm arm) {
    if (_exposed || widget.arm != null) return;
    _exposed = true;
    WidgetsBinding.instance.addPostFrameCallback((_) => SettingsPlanCardExperiment.recordExposure(arm));
  }

  @override
  Widget build(BuildContext context) {
    final usage = context.watch<UsageProvider>();
    final subscription = usage.subscription;
    final plan = subscription?.subscription.plan;
    if (subscription == null || !usage.showSubscriptionUI || (plan != PlanType.basic && plan != PlanType.plus)) {
      return widget.row;
    }
    final arm = _arm;
    if (arm == null) return widget.row;
    _expose(arm);
    final upgrade = OmiButton(
      key: const ValueKey('settings_plan_upgrade'),
      label: plan == PlanType.plus ? context.l10n.upgradeToUnlimited : context.l10n.upgrade,
      expand: true,
      onPressed: () => openSettingsUpgrade(context),
    );
    if (arm == SettingsPlanCardArm.control) {
      return _ControlSection(row: widget.row, subscription: subscription, upgrade: upgrade);
    }
    return _PlanCard(planName: widget.planName, onOpen: widget.onOpen, subscription: subscription, upgrade: upgrade);
  }
}

/// Control: the Plan & Usage row, then the minutes meter and a full-width Upgrade under it.
class _ControlSection extends StatelessWidget {
  const _ControlSection({required this.row, required this.subscription, required this.upgrade});

  final Widget row;
  final UserSubscriptionResponse subscription;
  final Widget upgrade;

  @override
  Widget build(BuildContext context) {
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
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, 0, OmiSpacing.lg, OmiSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (hasLimit) ...[
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
                const SizedBox(height: OmiSpacing.md),
              ],
              upgrade,
            ],
          ),
        ),
      ],
    );
  }
}

/// Test arm: a plan card with the plan name large, the minutes meter, then a full-width Upgrade.
class _PlanCard extends StatelessWidget {
  const _PlanCard({required this.planName, required this.onOpen, required this.subscription, required this.upgrade});

  final String? planName;
  final VoidCallback onOpen;
  final UserSubscriptionResponse subscription;
  final Widget upgrade;

  @override
  Widget build(BuildContext context) {
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
                  ExcludeSemantics(child: Icon(Icons.chevron_right, size: 20, color: OmiColors.textTertiary)),
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
                Text(
                  l10n.minsUsedThisMonth(NumberFormat.decimalPattern(l10n.localeName).format(used), limit),
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                ),
              ],
              const SizedBox(height: OmiSpacing.lg),
              upgrade,
            ],
          ),
        ),
      ),
    );
  }
}

/// The Settings Upgrade button: the paywall experiment's arm for the reader, else the plans sheet.
Future<void> openSettingsUpgrade(BuildContext context) => openUpgradePaywall(context, source: 'usage_page');
