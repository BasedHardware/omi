import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AllSetStep extends StatelessWidget {
  const AllSetStep({super.key, required this.onComplete, this.preferences});

  final VoidCallback onComplete;
  final SharedPreferencesUtil? preferences;

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<DeviceOnboardingProvider>();
    final prefs = preferences ?? SharedPreferencesUtil();
    final voiceMode = provider.selectedVoiceResponseMode ?? prefs.voiceResponseMode;
    final doubleTapAction =
        provider.selectedDoubleTapAction == -1 ? prefs.doubleTapAction : provider.selectedDoubleTapAction;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg),
      child: Column(
        children: [
          const SizedBox(height: OmiSpacing.lg),
          Text(context.l10n.deviceOnboardingAllSetTitle, style: OmiType.title1, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.xs),
          Text(
            context.l10n.deviceOnboardingAllSetSubtitle,
            style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.35),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: OmiSpacing.xl),
          DecoratedBox(
            decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
            child: Column(
              children: [
                _SummaryRow(
                  key: const Key('all_set_press_once'),
                  badge: context.l10n.deviceOnboardingAllSetSinglePressBadge,
                  title: context.l10n.deviceOnboardingAskQuestionTitle,
                  subtitle: context.l10n.deviceOnboardingAskQuestionSubtitle,
                  onTap: () => provider.goToStep(DeviceOnboardingProvider.askQuestionStep),
                ),
                const Divider(height: 1, color: OmiColors.border),
                _SummaryRow(
                  key: const Key('all_set_voice_reply'),
                  icon: Icons.headphones,
                  title: context.l10n.voiceResponseMode,
                  subtitle: _voiceModeLabel(context, voiceMode),
                  onTap: () => provider.goToStep(DeviceOnboardingProvider.voiceReplyStep),
                ),
                const Divider(height: 1, color: OmiColors.border),
                _SummaryRow(
                  key: const Key('all_set_double_tap'),
                  badge: context.l10n.deviceOnboardingAllSetDoublePressBadge,
                  title: context.l10n.doubleTap,
                  subtitle: _doubleTapLabel(context, doubleTapAction),
                  onTap: () => provider.goToStep(DeviceOnboardingProvider.doublePressStep),
                ),
                const Divider(height: 1, color: OmiColors.border),
                _SummaryRow(
                  key: const Key('all_set_hold'),
                  icon: Icons.power_settings_new,
                  title: context.l10n.deviceOnboardingTurnOffTitle,
                  subtitle: context.l10n.deviceOnboardingTurnOffSubtitle,
                  onTap: () => provider.goToStep(DeviceOnboardingProvider.powerCycleStep),
                ),
              ],
            ),
          ),
          const Spacer(),
          Text(
            context.l10n.deviceOnboardingAllSetReplayHint(
              context.l10n.settings,
              context.l10n.deviceSettings,
              context.l10n.deviceTutorial,
            ),
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: OmiSpacing.sm),
          OmiButton(
            key: const Key('all_set_finish'),
            label: context.l10n.deviceOnboardingFinish,
            onPressed: onComplete,
            expand: true,
            labelStyle: OmiType.callout.copyWith(fontWeight: FontWeight.w600, fontFamily: 'Roboto'),
          ),
          const SizedBox(height: OmiSpacing.lg),
        ],
      ),
    );
  }

  String _voiceModeLabel(BuildContext context, int mode) => switch (mode) {
        0 => context.l10n.voiceResponseOff,
        2 => context.l10n.voiceResponseAlways,
        _ => context.l10n.voiceResponseHeadphonesOnly,
      };

  String _doubleTapLabel(BuildContext context, int action) => switch (action) {
        1 => context.l10n.deviceOnboardingMuteUnmute,
        2 => context.l10n.deviceOnboardingStarConversation,
        _ => context.l10n.deviceOnboardingEndConversation,
      };
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow({
    super.key,
    this.badge,
    this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  }) : assert(badge != null || icon != null);

  final String? badge;
  final IconData? icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 72),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
              child: Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: const BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
                    alignment: Alignment.center,
                    child: icon == null
                        ? Text(badge!, style: OmiType.footnote.copyWith(fontWeight: FontWeight.w700))
                        : Icon(icon, size: 20, color: OmiColors.textPrimary),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                        const SizedBox(height: OmiSpacing.xxs),
                        Text(subtitle, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                      ],
                    ),
                  ),
                  const Icon(Icons.chevron_right, size: 20, color: OmiColors.textTertiary),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
