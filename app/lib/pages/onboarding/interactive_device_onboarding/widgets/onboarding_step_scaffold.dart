import 'package:flutter/material.dart';

import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

// Persistent, self-animating progress indicator. Rendered once in the wrapper
// (above the transitioning content) and driven live by provider.currentStep, so
// the active dot grows in place as the flow advances instead of being duplicated
// inside each step and sliding away with it.
class OnboardingProgressDots extends StatelessWidget {
  final int currentStep;

  const OnboardingProgressDots({super.key, required this.currentStep});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(DeviceOnboardingProvider.totalSteps, (index) {
        // v2: one short bar per step, filled up to the current one (same as first-run onboarding).
        return AnimatedContainer(
          duration: OmiMotion.of(context).standard,
          curve: OmiMotion.springCurve,
          margin: const EdgeInsets.symmetric(horizontal: 2.5),
          width: 16,
          height: 3,
          decoration: BoxDecoration(
            borderRadius: OmiRadius.pillAll,
            color: index <= currentStep ? OmiColors.textPrimary : OmiColors.surface3,
          ),
        );
      }),
    );
  }
}

class OnboardingStepScaffold extends StatelessWidget {
  final String title;
  final String subtitle;
  final Widget content;
  final Widget? bottomAction;

  const OnboardingStepScaffold({
    super.key,
    required this.title,
    required this.subtitle,
    required this.content,
    this.bottomAction,
  });

  @override
  Widget build(BuildContext context) {
    // v2: the title left-aligned at the top, the step's content, the action pinned at the bottom.
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: OmiSpacing.xl),
          Semantics(header: true, child: Text(title, style: OmiType.title1)),
          if (subtitle.isNotEmpty) ...[
            const SizedBox(height: OmiSpacing.xs),
            Text(subtitle, style: OmiType.body.copyWith(color: OmiColors.textSecondary, height: 1.4)),
          ],
          const SizedBox(height: OmiSpacing.xxl),
          Expanded(child: content),
          if (bottomAction != null) ...[bottomAction!, const SizedBox(height: OmiSpacing.xl)],
        ],
      ),
    );
  }
}

class OnboardingContinueButton extends StatelessWidget {
  final VoidCallback onPressed;
  final String? label;

  const OnboardingContinueButton({super.key, required this.onPressed, this.label});

  @override
  Widget build(BuildContext context) {
    return OmiButton(
      label: label ?? context.l10n.deviceOnboardingContinue,
      expand: true,
      onPressed: onPressed,
    );
  }
}
