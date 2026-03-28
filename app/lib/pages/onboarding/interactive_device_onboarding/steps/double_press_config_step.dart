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
              const SizedBox(height: 24),
              const DoubleTapDemoAnimation(),
              const Spacer(),
              if (!provider.doublePressDetected) ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  decoration: BoxDecoration(
                    color: provider.showSingleTapHint
                        ? const Color(0xFFFFA726).withValues(alpha: 0.12)
                        : Colors.white.withValues(alpha: 0.06),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.touch_app,
                          color: provider.showSingleTapHint ? const Color(0xFFFFA726) : Colors.white.withValues(alpha: 0.6),
                          size: 24),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          provider.showSingleTapHint
                              ? 'That was a single tap — try tapping twice quickly!'
                              : 'Try it now! Double tap your Omi',
                          style: TextStyle(
                              color: provider.showSingleTapHint ? const Color(0xFFFFA726) : const Color(0xFF9E9E9E),
                              fontSize: 15),
                        ),
                      ),
                    ],
                  ),
                ),
              ] else ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                  decoration: BoxDecoration(
                    color: const Color(0xFF4CAF50).withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.check_circle, color: Color(0xFF4CAF50), size: 22),
                      SizedBox(width: 10),
                      Text('Double tap detected!', style: TextStyle(color: Color(0xFF4CAF50), fontSize: 16, fontWeight: FontWeight.w600)),
                    ],
                  ),
                ),
              ],
            ],
          ),
          bottomAction: provider.doublePressDetected
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
          borderRadius: BorderRadius.circular(100),
          border: Border.all(
            color: isSelected ? Colors.white : Colors.white.withValues(alpha: 0.1),
            width: 1,
          ),
        ),
        child: Row(
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
                      style: TextStyle(color: isSelected ? Colors.black.withValues(alpha: 0.5) : const Color(0xFF9E9E9E), fontSize: 13)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
