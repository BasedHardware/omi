import 'package:flutter/material.dart';

import 'package:omi/providers/device_onboarding_provider.dart';

class OnboardingStepScaffold extends StatelessWidget {
  final String title;
  final String subtitle;
  final Widget content;
  final Widget? bottomAction;
  final int currentStep;

  const OnboardingStepScaffold({
    super.key,
    required this.title,
    required this.subtitle,
    required this.content,
    required this.currentStep,
    this.bottomAction,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: Column(
          children: [
            const SizedBox(height: 16),
            _buildProgressDots(),
            const SizedBox(height: 40),
            Text(
              title,
              style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.bold),
              textAlign: TextAlign.center,
            ),
            if (subtitle.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                subtitle,
                style: const TextStyle(color: Color(0xFF9E9E9E), fontSize: 16, height: 1.4),
                textAlign: TextAlign.center,
              ),
            ],
            const SizedBox(height: 40),
            Expanded(child: content),
            if (bottomAction != null) ...[
              bottomAction!,
              const SizedBox(height: 24),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildProgressDots() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(DeviceOnboardingProvider.totalSteps, (index) {
        final isActive = index == currentStep;
        final isCompleted = index < currentStep;
        return Container(
          margin: const EdgeInsets.symmetric(horizontal: 4),
          width: isActive ? 24 : 8,
          height: 8,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(4),
            color: isActive
                ? Colors.white
                : isCompleted
                    ? Colors.white.withValues(alpha: 0.5)
                    : Colors.white.withValues(alpha: 0.2),
          ),
        );
      }),
    );
  }
}

class OnboardingContinueButton extends StatelessWidget {
  final VoidCallback onPressed;
  final String label;

  const OnboardingContinueButton({
    super.key,
    required this.onPressed,
    this.label = 'Continue',
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: ElevatedButton(
        onPressed: onPressed,
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.white,
          foregroundColor: Colors.black,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
          elevation: 0,
        ),
        child: Text(label, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
      ),
    );
  }
}
