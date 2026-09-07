import 'package:flutter/material.dart';

/// A row of white capsule segments for the onboarding flow's header, one per
/// step, replacing a single continuous bar. Each segment eases toward its
/// new fill amount whenever [currentStep] advances instead of snapping.
class OnboardingProgressBar extends StatelessWidget {
  final int currentStep;
  final int totalSteps;

  const OnboardingProgressBar({super.key, required this.currentStep, required this.totalSteps});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: List.generate(totalSteps, (index) {
        final fill = index <= currentStep ? 1.0 : 0.0;
        return Expanded(
          child: Container(
            margin: EdgeInsets.only(right: index == totalSteps - 1 ? 0 : 4),
            height: 6,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(3),
              color: Colors.white.withValues(alpha: 0.2),
            ),
            alignment: Alignment.centerLeft,
            child: TweenAnimationBuilder<double>(
              tween: Tween<double>(begin: 0, end: fill),
              duration: const Duration(milliseconds: 450),
              curve: Curves.easeOutCubic,
              builder: (context, value, child) {
                return FractionallySizedBox(widthFactor: value, alignment: Alignment.centerLeft, child: child);
              },
              child: ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: Container(color: Colors.white),
              ),
            ),
          ),
        );
      }),
    );
  }
}
