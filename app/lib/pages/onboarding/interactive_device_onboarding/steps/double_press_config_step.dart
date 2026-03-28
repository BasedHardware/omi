import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/device_onboarding_provider.dart';
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
          subtitle: provider.doublePressDetected
              ? 'Double tap detected! You\'re all set.'
              : 'Choose what happens when you double tap your Omi',
          currentStep: 3,
          content: Column(
            children: [
              _buildOptionCard(
                provider: provider,
                action: 0,
                icon: Icons.stop_circle_outlined,
                title: 'End Conversation',
                description: 'Double tap to end and save the current conversation',
              ),
              const SizedBox(height: 12),
              _buildOptionCard(
                provider: provider,
                action: 1,
                icon: Icons.mic_off,
                title: 'Mute / Unmute',
                description: 'Double tap to toggle microphone on/off',
              ),
              const SizedBox(height: 12),
              _buildOptionCard(
                provider: provider,
                action: 2,
                icon: Icons.star_outline,
                title: 'Star Conversation',
                description: 'Double tap to mark the current conversation as important',
              ),
              const Spacer(),
              if (!provider.doublePressDetected) ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.06),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.touch_app, color: Colors.white.withValues(alpha: 0.6), size: 24),
                      const SizedBox(width: 12),
                      const Expanded(
                        child: Text(
                          'Try it now! Double tap your Omi',
                          style: TextStyle(color: Color(0xFF9E9E9E), fontSize: 15),
                        ),
                      ),
                    ],
                  ),
                ),
              ] else ...[
                const Icon(Icons.check_circle, color: Color(0xFF4CAF50), size: 48),
                const SizedBox(height: 8),
                const Text('Double tap detected!', style: TextStyle(color: Color(0xFF4CAF50), fontSize: 16)),
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
          color: isSelected ? Colors.white.withValues(alpha: 0.1) : Colors.white.withValues(alpha: 0.04),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isSelected ? Colors.white.withValues(alpha: 0.4) : Colors.white.withValues(alpha: 0.1),
            width: isSelected ? 2 : 1,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: isSelected ? Colors.white.withValues(alpha: 0.15) : Colors.white.withValues(alpha: 0.06),
              ),
              child: Icon(icon, color: isSelected ? Colors.white : const Color(0xFF9E9E9E), size: 24),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(description, style: const TextStyle(color: Color(0xFF9E9E9E), fontSize: 13)),
                ],
              ),
            ),
            if (isSelected) const Icon(Icons.check_circle, color: Colors.white, size: 22),
          ],
        ),
      ),
    );
  }
}
