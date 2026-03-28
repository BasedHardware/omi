import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/double_tap_demo_animation.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';

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
          title: 'Customize Double Tap',
          subtitle: '',
          currentStep: 3,
          content: Column(
            children: [
              _buildOptionCard(
                provider: provider,
                action: 0,
                icon: Icons.stop_circle_outlined,
                title: 'End Conversation',
                description: 'Save and end current conversation',
              ),
              const SizedBox(height: 12),
              _buildOptionCard(
                provider: provider,
                action: 1,
                icon: Icons.mic_off,
                title: 'Mute / Unmute',
                description: 'Toggle microphone on or off',
              ),
              const SizedBox(height: 12),
              _buildOptionCard(
                provider: provider,
                action: 2,
                icon: Icons.star_outline,
                title: 'Star Conversation',
                description: 'Mark conversation as important',
              ),
              const Spacer(),
              if (provider.showSingleTapHint) ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFA726).withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: const Row(
                    children: [
                      Icon(Icons.touch_app, color: Color(0xFFFFA726), size: 24),
                      SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          'That was a single tap — try tapping twice quickly!',
                          style: TextStyle(color: Color(0xFFFFA726), fontSize: 15),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
          bottomAction: provider.doublePressCount > 0 && !provider.showSingleTapHint
              ? OnboardingContinueButton(label: 'Finish', onPressed: widget.onComplete)
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
          color: isSelected ? Colors.white : Colors.white.withValues(alpha: 0.04),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: isSelected ? Colors.white : Colors.white.withValues(alpha: 0.1),
            width: 1,
          ),
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
                    color: isSelected ? Colors.black.withValues(alpha: 0.1) : Colors.white.withValues(alpha: 0.06),
                  ),
                  child: Icon(icon, color: isSelected ? Colors.black : const Color(0xFF9E9E9E), size: 24),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          color: isSelected ? Colors.black : Colors.white,
                          fontSize: 16,
                          fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(description,
                          style: TextStyle(
                              color: isSelected ? Colors.black.withValues(alpha: 0.5) : const Color(0xFF9E9E9E),
                              fontSize: 13)),
                    ],
                  ),
                ),
              ],
            ),
            if (isSelected) ...[
              const SizedBox(height: 12),
              _buildInlineDemo(action, provider.doublePressCount),
            ],
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
