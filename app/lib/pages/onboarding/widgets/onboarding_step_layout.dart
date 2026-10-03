import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// The host owns space for navigation above steps that start at the top of the screen.
/// Bottom-card steps can keep their navigation over the background artwork.
class OnboardingStepLayout extends StatelessWidget {
  const OnboardingStepLayout({
    super.key,
    required this.child,
    required this.reserveHeader,
    this.progress,
    this.onBack,
  });

  final Widget child;
  final bool reserveHeader;
  final Widget? progress;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    final chrome = Stack(children: [
      if (progress != null) Padding(padding: const EdgeInsets.only(top: OmiSpacing.md), child: progress!),
      if (onBack != null)
        Padding(
          padding: const EdgeInsets.only(left: OmiSpacing.xs, top: OmiSpacing.xxs),
          child: Align(
            alignment: Alignment.topLeft,
            child: OmiBackButton.circled(key: const Key('onboarding_back'), onPressed: onBack),
          ),
        ),
    ]);
    if (reserveHeader) {
      return Column(children: [
        SafeArea(
          bottom: false,
          child: SizedBox(height: OmiSpacing.md + kOmiMinTapTarget, child: chrome),
        ),
        Expanded(child: MediaQuery.removePadding(context: context, removeTop: true, child: child)),
      ]);
    }
    return Stack(children: [child, if (progress != null || onBack != null) SafeArea(child: chrome)]);
  }
}
