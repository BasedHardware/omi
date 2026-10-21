import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/double_tap_demo_animation.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
import 'package:omi/utils/l10n_extensions.dart';

class DoublePressConfigStep extends StatefulWidget {
  final VoidCallback onComplete;

  const DoublePressConfigStep({super.key, required this.onComplete});

  @override
  State<DoublePressConfigStep> createState() => _DoublePressConfigStepState();
}

class _DoublePressConfigStepState extends State<DoublePressConfigStep> {
  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceOnboardingProvider>(
      builder: (context, provider, _) {
        return OnboardingStepScaffold(
          title: context.l10n.deviceOnboardingDoubleTapTitle,
          subtitle: '',
          content: Column(
            children: [
              _buildOptionCard(
                provider: provider,
                action: 0,
                icon: Icons.stop_circle_outlined,
                title: context.l10n.deviceOnboardingEndConversation,
                description: context.l10n.deviceOnboardingEndConversationDesc,
              ),
              const SizedBox(height: 12),
              _buildOptionCard(
                provider: provider,
                action: 1,
                icon: Icons.mic_off,
                title: context.l10n.deviceOnboardingMuteUnmute,
                description: context.l10n.deviceOnboardingMuteUnmuteDesc,
              ),
              const SizedBox(height: 12),
              _buildOptionCard(
                provider: provider,
                action: 2,
                icon: Icons.star_outline,
                title: context.l10n.deviceOnboardingStarConversation,
                description: context.l10n.deviceOnboardingStarConversationDesc,
              ),
              const Spacer(),
              if (provider.showSingleTapHint) ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFA726).withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.touch_app, color: Color(0xFFFFA726), size: 24),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          context.l10n.deviceOnboardingSingleTapHint,
                          style: const TextStyle(color: Color(0xFFFFA726), fontSize: 15),
                        ),
                      ),
                    ],
                  ),
                ),
              ] else if (provider.selectedDoubleTapAction != -1 && provider.doublePressCount == 0) ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  decoration: BoxDecoration(
                    color: OmiColors.surface1,
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.touch_app, color: OmiColors.textSecondary, size: 24),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          context.l10n.deviceOnboardingTryDoubleTap,
                          style: TextStyle(color: OmiColors.textSecondary, fontSize: 15),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
          bottomAction: provider.doublePressCount > 0 && !provider.showSingleTapHint
              ? OnboardingContinueButton(onPressed: widget.onComplete)
              : null,
        );
      },
    );
  }

  Widget _buildOptionCard({
    required DeviceOnboardingProvider provider,
    required int action,
    required IconData icon,
    required String title,
    required String description,
  }) {
    final isSelected = provider.selectedDoubleTapAction == action;

    return GestureDetector(
      onTap: () => provider.selectDoubleTapAction(action),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isSelected ? OmiColors.accent : OmiColors.surface1,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: isSelected ? OmiColors.accent : OmiColors.border, width: 1),
        ),
        child: Column(
          children: [
            Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: isSelected ? OmiColors.onAccent.withValues(alpha: 0.1) : OmiColors.surface2,
                  ),
                  child: Icon(icon, color: isSelected ? OmiColors.onAccent : OmiColors.textSecondary, size: 24),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          color: isSelected ? OmiColors.onAccent : OmiColors.textPrimary,
                          fontSize: 16,
                          fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        description,
                        style: TextStyle(
                          color: isSelected ? OmiColors.onAccent.withValues(alpha: 0.6) : OmiColors.textSecondary,
                          fontSize: 13,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            if (isSelected) ...[const SizedBox(height: 12), _buildInlineDemo(action, provider.doublePressCount)],
          ],
        ),
      ),
    );
  }

  Widget _buildInlineDemo(int action, int doublePressCount) {
    switch (action) {
      case 0:
        return EndConversationDemo(doublePressCount: doublePressCount);
      case 1:
        return MuteUnmuteDemo(doublePressCount: doublePressCount);
      case 2:
        return StarConversationDemo(doublePressCount: doublePressCount);
      default:
        return const SizedBox.shrink();
    }
  }
}
